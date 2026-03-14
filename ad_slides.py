import pygame
import json
from datetime import datetime, timedelta
from PIL import Image
from gesture import GestureControl
import os
from arabic_reshaper import reshape
from bidi.algorithm import get_display
import time
import cv2
import subprocess
import re

pygame.init()
pygame.font.init()
pygame.mixer.init()

# Configuration
URGENT_VOICE_FILE = "luvvoice.com-20251129-MWN5ah.mp3"
ARABIC_FONT_FILE = "IBMPlexSansArabic-Regular.ttf"

# Try to import pygame_emojis
try:
    from pygame_emojis import load_emoji
    EMOJI_SUPPORT = True
except ImportError:
    print("Warning: pygame_emojis not installed. Emoji rendering disabled.")
    EMOJI_SUPPORT = False


def is_emoji(char):
    """Check if a character is an emoji"""
    code = ord(char)
    return (
        0x1F300 <= code <= 0x1F9FF or  # Emoticons, symbols, pictographs
        0x2600 <= code <= 0x27BF or    # Misc symbols
        0x1F000 <= code <= 0x1F02F or  # Mahjong tiles
        0x1F0A0 <= code <= 0x1F0FF or  # Playing cards
        0x1F100 <= code <= 0x1F64F or  # Enclosed characters
        0x1F680 <= code <= 0x1F6FF or  # Transport symbols
        0x1F900 <= code <= 0x1F9FF or  # Supplemental symbols
        0x2700 <= code <= 0x27BF or    # Dingbats
        0xFE00 <= code <= 0xFE0F or    # Variation selectors
        0x1F1E6 <= code <= 0x1F1FF     # Regional indicators (flags)
    )


def extract_text_and_emojis(text):
    """Split text into segments of regular text and emojis"""
    segments = []
    current_text = ""
    
    i = 0
    while i < len(text):
        char = text[i]
        
        if is_emoji(char):
            # Save accumulated text
            if current_text:
                segments.append({"type": "text", "content": current_text})
                current_text = ""
            
            # Check for compound emojis (with ZWJ or variation selectors)
            emoji_str = char
            j = i + 1
            while j < len(text):
                next_char = text[j]
                next_code = ord(next_char)
                # Zero Width Joiner or variation selectors
                if next_code == 0x200D or 0xFE00 <= next_code <= 0xFE0F:
                    emoji_str += next_char
                    j += 1
                elif is_emoji(next_char):
                    emoji_str += next_char
                    j += 1
                else:
                    break
            
            segments.append({"type": "emoji", "content": emoji_str})
            i = j
        else:
            current_text += char
            i += 1
    
    # Save remaining text
    if current_text:
        segments.append({"type": "text", "content": current_text})
    
    return segments


def render_text_with_emojis(text, font, text_color=(255, 255, 255), emoji_size=None):
    """Render text with emojis as a pygame surface"""
    if not EMOJI_SUPPORT or not any(is_emoji(c) for c in text):
        # No emojis or no support, render normally
        return font.render(text, True, text_color)
    
    # Determine emoji size based on font size
    if emoji_size is None:
        emoji_size = int(font.get_height() * 1.2)
    
    segments = extract_text_and_emojis(text)
    
    # Calculate total width
    total_width = 0
    max_height = font.get_height()
    rendered_segments = []
    
    for segment in segments:
        if segment["type"] == "text":
            if segment["content"].strip():
                surf = font.render(segment["content"], True, text_color)
                rendered_segments.append({"surface": surf, "type": "text"})
                total_width += surf.get_width()
                max_height = max(max_height, surf.get_height())
        else:  # emoji
            try:
                emoji_surf = load_emoji(segment["content"], (emoji_size, emoji_size))
                rendered_segments.append({"surface": emoji_surf, "type": "emoji"})
                total_width += emoji_surf.get_width()
                max_height = max(max_height, emoji_surf.get_height())
            except Exception as e:
                # Fallback: render as text
                surf = font.render(segment["content"], True, text_color)
                rendered_segments.append({"surface": surf, "type": "text"})
                total_width += surf.get_width()
    
    # Create combined surface
    combined_surface = pygame.Surface((max(1, total_width), max_height), pygame.SRCALPHA)
    combined_surface.fill((0, 0, 0, 0))
    
    # Blit all segments
    x_offset = 0
    for segment in rendered_segments:
        surf = segment["surface"]
        # Center vertically
        y_offset = (max_height - surf.get_height()) // 2
        combined_surface.blit(surf, (x_offset, y_offset))
        x_offset += surf.get_width()
    
    return combined_surface


def load_arabic_font(size=36):
    """Load Arabic-compatible font with fallback options"""
    if os.path.exists(ARABIC_FONT_FILE):
        try:
            return pygame.font.Font(ARABIC_FONT_FILE, size)
        except Exception as e:
            print(f"Error loading Arabic font: {e}")
    
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                return pygame.font.Font(font_path, size)
            except:
                continue
    
    return pygame.font.Font(None, size)


def extract_audio_from_video(video_path):
    """Extract audio from video file and save it in the same directory"""
    video_dir = os.path.dirname(video_path)
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    audio_file = os.path.join(video_dir, f"{video_name}_audio.wav")
    
    if os.path.exists(audio_file):
        return audio_file
    
    try:
        print(f"Extracting audio from {video_path}...")
        subprocess.run([
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
            audio_file
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Audio extracted to {audio_file}")
        return audio_file
    except Exception as e:
        print(f"Error extracting audio: {e}")
        return None


def load_posts(json_file="posts_history.json"):
    """Load and filter posts from JSON, removing expired entries"""
    try:
        with open(json_file, "r", encoding='utf-8') as f:
            posts = json.load(f)
    except Exception as e:
        return []

    valid_posts = []
    remaining_posts = []
    now = datetime.now()

    for idx, post in enumerate(posts):
        status = post.get("status", "ordinary")
        media = post.get("media_path") or ""
        media = media.strip() if media else ""
        
        timestamp = post.get("timestamp")
        text = post.get("text", "").strip()

        if not media and not text:
            continue
            
        if not timestamp:
            continue

        try:
            post_time = datetime.strptime(timestamp, "%Y%m%d%H%M%S")
        except ValueError as e:
            continue

        time_diff = now - post_time
        expiry_hours = 3 if status == "urgent" else 24
        expired = time_diff > timedelta(hours=expiry_hours)

        if expired:
            if media:
                media_path = media if os.path.isabs(media) else os.path.join(os.getcwd(), "static", media)
                if os.path.exists(media_path):
                    try:
                        os.remove(media_path)
                        print(f"Deleted expired media: {media_path}")
                    except Exception as e:
                        print(f"Error deleting media: {e}")
            print(f"Removed expired post: {timestamp}")
            continue

        is_text_only = not media
        
        if not is_text_only:
            if not os.path.isabs(media):
                media = os.path.join(os.getcwd(), "static", media)

            if not os.path.exists(media):
                is_text_only = True
                media = ""

        is_video = False
        if media:
            ext = os.path.splitext(media)[1].lower()
            is_video = ext in [".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"]

        valid_posts.append({
            "media": media,
            "caption": text,
            "urgent": (status == "urgent"),
            "is_video": is_video,
            "is_text_only": is_text_only,
            "timestamp": timestamp
        })
        remaining_posts.append(post)

    try:
        with open(json_file, "w", encoding='utf-8') as f:
            json.dump(remaining_posts, f, indent=4, ensure_ascii=False)
        print(f"Saved {len(remaining_posts)} posts to JSON")
    except Exception as e:
        print(f"Error saving posts: {e}")
    
    return valid_posts


def draw_rounded_rect(surface, color, rect, radius):
    """Draw a rounded rectangle"""
    x, y, width, height = rect
    
    pygame.draw.rect(surface, color, (x + radius, y, width - 2*radius, height))
    pygame.draw.rect(surface, color, (x, y + radius, width, height - 2*radius))
    
    pygame.draw.circle(surface, color, (x + radius, y + radius), radius)
    pygame.draw.circle(surface, color, (x + width - radius, y + radius), radius)
    pygame.draw.circle(surface, color, (x + radius, y + height - radius), radius)
    pygame.draw.circle(surface, color, (x + width - radius, y + height - radius), radius)


def wrap_text(text, font, max_width):
    """Wrap text to fit within max_width, handling newlines, Arabic text, and emojis"""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    paragraphs = text.split('\n')
    lines = []
    
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        
        if not paragraph:
            lines.append(' ')
            continue
        
        has_arabic = any('\u0600' <= char <= '\u06FF' for char in paragraph)
        has_emoji = EMOJI_SUPPORT and any(is_emoji(char) for char in paragraph)
        
        if has_arabic:
            try:
                reshaped_text = reshape(paragraph)
                bidi_text = get_display(reshaped_text)
            except Exception as e:
                print(f"Error processing Arabic text: {e}")
                bidi_text = paragraph
            
            # Check width with emoji rendering if needed
            if has_emoji:
                test_surface = render_text_with_emojis(bidi_text, font)
                text_width = test_surface.get_width()
            else:
                text_width = font.size(bidi_text)[0]
            
            if text_width <= max_width:
                lines.append(bidi_text)
            else:
                # Split by words
                words = paragraph.split(' ')
                current_words = []
                
                for word in words:
                    if not word.strip():
                        continue
                    
                    test_paragraph = ' '.join(current_words + [word])
                    test_reshaped = reshape(test_paragraph)
                    test_bidi = get_display(test_reshaped)
                    
                    if has_emoji:
                        test_surface = render_text_with_emojis(test_bidi, font)
                        test_width = test_surface.get_width()
                    else:
                        test_width = font.size(test_bidi)[0]
                    
                    if test_width <= max_width:
                        current_words.append(word)
                    else:
                        if current_words:
                            line_text = ' '.join(current_words)
                            line_reshaped = reshape(line_text)
                            line_bidi = get_display(line_reshaped)
                            lines.append(line_bidi)
                        current_words = [word]
                
                if current_words:
                    line_text = ' '.join(current_words)
                    line_reshaped = reshape(line_text)
                    line_bidi = get_display(line_reshaped)
                    lines.append(line_bidi)
        else:
            # English or other languages
            if has_emoji:
                test_surface = render_text_with_emojis(paragraph, font)
                text_width = test_surface.get_width()
            else:
                text_width = font.size(paragraph)[0]
            
            if text_width <= max_width:
                lines.append(paragraph)
            else:
                words = paragraph.split(' ')
                current_line = []
                
                for word in words:
                    if not word:
                        continue
                    
                    test_line = ' '.join(current_line + [word])
                    
                    if has_emoji:
                        test_surface = render_text_with_emojis(test_line, font)
                        test_width = test_surface.get_width()
                    else:
                        test_width = font.size(test_line)[0]
                    
                    if test_width <= max_width:
                        current_line.append(word)
                    else:
                        if current_line:
                            lines.append(' '.join(current_line))
                        current_line = [word]
                
                if current_line:
                    lines.append(' '.join(current_line))
    
    return lines


class VoiceManager:
    """Manages voice playback for urgent ads"""
    
    def __init__(self, voice_file):
        self.voice_file = voice_file
        self.voice_available = os.path.exists(voice_file)
        self.voice_states = {}
        
        if not self.voice_available:
            print(f"Warning: Voice file not found: {voice_file}")
    
    def register_urgent_ad(self, timestamp):
        if not self.voice_available or timestamp in self.voice_states:
            return

        try:
            post_time = datetime.strptime(timestamp, "%Y%m%d%H%M%S")
        except ValueError:
            return

        now = datetime.now()
        age = now - post_time

        play_times = []
        if age <= timedelta(hours=3):
            # Play immediately if < 3h old
            if age < timedelta(minutes=5):  # just posted
                play_times.append(now)
            # Then schedule +1h, +2h if within window
            for h in [1, 2]:
                scheduled = post_time + timedelta(hours=h)
                if scheduled <= post_time + timedelta(hours=3):
                    play_times.append(scheduled)

        if not play_times:
            return

        self.voice_states[timestamp] = {
            "play_times": play_times,
            "played_count": 0,
            "last_check": None
        }
        print(f"Registered urgent ad voice: {len(play_times)} plays for {timestamp}")
    
    def should_play_voice(self, timestamp):
        """Check if voice should play for this timestamp at current time"""
        if not self.voice_available or timestamp not in self.voice_states:
            return False
        
        state = self.voice_states[timestamp]
        now = datetime.now()
        
        if state["played_count"] < len(state["play_times"]):
            next_play_time = state["play_times"][state["played_count"]]
            
            if now >= next_play_time:
                if state["last_check"] is None or state["last_check"] < next_play_time:
                    state["last_check"] = now
                    return True
        
        return False
    
    def mark_played(self, timestamp):
        """Mark that voice has been played once"""
        if timestamp in self.voice_states:
            self.voice_states[timestamp]["played_count"] += 1
            print(f"Voice played {self.voice_states[timestamp]['played_count']}/3 for {timestamp}")
    
    def play_voice(self):
        """Play the general voice file"""
        if not self.voice_available:
            return False
        
        try:
            pygame.mixer.music.load(self.voice_file)
            pygame.mixer.music.play()
            print(f"Playing urgent voice: {self.voice_file}")
            return True
        except Exception as e:
            print(f"Error playing voice: {e}")
            return False
    
    def cleanup_expired(self):
        """Remove voice states for expired posts"""
        now = datetime.now()
        expired = []
        
        for timestamp in self.voice_states:
            try:
                post_time = datetime.strptime(timestamp, "%Y%m%d%H%M%S")
                if now - post_time > timedelta(hours=3):
                    expired.append(timestamp)
            except ValueError:
                expired.append(timestamp)
        
        for ts in expired:
            print(f"Removing expired voice state for {ts}")
            del self.voice_states[ts]


class VideoPlayer:
    """OpenCV-based video player with audio sync"""
    
    def __init__(self, video_path, screen_size):
        self.video_path = video_path
        self.screen_size = screen_size
        self.cap = None
        self.audio_file = None
        self.playing = False
        self.finished = False
        self.fps = 30
        self.frame_count = 0
        self.current_frame = 0
        self.start_time = None
        self.current_surface = None
        
        self._initialize()
    
    def _initialize(self):
        """Initialize video capture and extract audio"""
        try:
            self.cap = cv2.VideoCapture(self.video_path)
            if not self.cap.isOpened():
                print(f"Error: Cannot open video {self.video_path}")
                return
            
            self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
            self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            self.audio_file = extract_audio_from_video(self.video_path)
            
            print(f"Video initialized: {self.fps:.2f} fps, {self.frame_count} frames")
        except Exception as e:
            print(f"Error initializing video: {e}")
    
    def play(self):
        """Start playing video and audio"""
        if not self.cap or not self.cap.isOpened():
            return

        self.playing = True
        self.finished = False
        self.current_frame = 0
        self.start_time = time.time()  # Critical: mark start time

        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

        if self.audio_file and os.path.exists(self.audio_file):
            try:
                pygame.mixer.music.load(self.audio_file)
                pygame.mixer.music.play()
                print(f"Audio started: {self.audio_file}")
            except Exception as e:
                print(f"Error playing audio: {e}")
    
    def stop(self):
        """Stop playing"""
        self.playing = False
        try:
            pygame.mixer.music.stop()
        except:
            pass
    
    def get_frame(self):
        """Get current video frame as pygame surface, synchronized with real-time"""
        if not self.playing or not self.cap or not self.cap.isOpened():
            return None

        if self.current_frame >= self.frame_count:
            self.finished = True
            self.playing = False
            pygame.mixer.music.stop()
            return self.current_surface

        # Calculate expected time based on frame number and FPS
        expected_time = self.current_frame / self.fps
        elapsed_time = time.time() - self.start_time

        # Wait if we're too fast
        if elapsed_time < expected_time:
            time.sleep(expected_time - elapsed_time)

        ret, frame = self.cap.read()
        if not ret:
            self.finished = True
            self.playing = False
            pygame.mixer.music.stop()
            return self.current_surface

        # Resize and convert frame
        frame_h, frame_w = frame.shape[:2]
        screen_w, screen_h = self.screen_size

        scale_w = screen_w / frame_w
        scale_h = screen_h / frame_h
        scale = min(scale_w, scale_h)

        new_w = int(frame_w * scale)
        new_h = int(frame_h * scale)

        frame = cv2.resize(frame, (new_w, new_h))
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        self.current_surface = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
        self.current_frame += 1

        return self.current_surface
    
    def get_position(self):
        """Get centered position for drawing"""
        if not self.current_surface:
            return (0, 0)
        
        surf_w, surf_h = self.current_surface.get_size()
        screen_w, screen_h = self.screen_size
        
        x = (screen_w - surf_w) // 2
        y = (screen_h - surf_h) // 2
        
        return (x, y)
    
    def is_finished(self):
        """Check if video playback is finished"""
        return self.finished
    
    def cleanup(self):
        """Release resources"""
        self.stop()
        if self.cap:
            self.cap.release()


class MediaSlide:
    """Single slide containing media (image/video) and caption"""
    
    def __init__(self, screen, source, caption, is_video=False, slide_index=None, 
                 is_urgent=False, timestamp=None, is_text_only=False):
        self.screen = screen
        self.source = source
        self.caption = caption
        self.is_video = is_video
        self.slide_index = slide_index
        self.surface = None
        self.is_urgent = is_urgent
        self.timestamp = timestamp
        self.is_text_only = is_text_only
        
        self.video_player = None
        
        if not is_text_only:
            if is_video:
                self.load_video()
            else:
                self.load_image()
    
    def load_image(self):
        """Load image and scale to fit screen"""
        try:
            img = Image.open(self.source)
            if img.mode != 'RGB':
                img = img.convert('RGB')

            screen_width, screen_height = self.screen.get_size()
            img_w, img_h = img.size

            img_ratio = img_w / img_h
            screen_ratio = screen_width / screen_height

            if img_w > img_h:
                new_w = screen_width
                new_h = int(screen_width / img_ratio)
                if new_h > screen_height:
                    new_h = screen_height
                    new_w = int(screen_height * img_ratio)
            else:
                new_h = screen_height
                new_w = int(screen_height * img_ratio)
                if new_w > screen_width:
                    new_w = screen_width
                    new_h = int(screen_width / img_ratio)

            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            img_str = img.tobytes()
            self.surface = pygame.image.fromstring(img_str, img.size, 'RGB')

        except Exception as e:
            print(f"Error loading image {self.source}: {e}")
            self.surface = None

    def load_video(self):
        """Initialize video player"""
        try:
            screen_size = self.screen.get_size()
            self.video_player = VideoPlayer(self.source, screen_size)
        except Exception as e:
            print(f"Error initializing video: {e}")
            self.video_player = None
    
    def play_video(self):
        """Start playing video"""
        if self.video_player:
            self.video_player.play()
    
    def stop_video(self):
        """Stop playing video"""
        if self.video_player:
            self.video_player.stop()
    
    def is_video_finished(self):
        """Check if video has finished"""
        if self.video_player:
            return self.video_player.is_finished()
        return False
    
    def draw(self):
        """Draw the slide"""
        screen_width, screen_height = self.screen.get_size()
        self.screen.fill((0, 0, 0))
        
        if self.is_text_only:
            content_font = load_arabic_font(48)
            text_color = (255, 255, 255)
            max_width = screen_width - 100
            lines = wrap_text(self.caption, content_font, max_width)
            line_height = 60
            total_height = len(lines) * line_height
            y_offset = (screen_height - total_height) // 2
            
            for line in lines:
                text_surface = render_text_with_emojis(line, content_font, text_color)
                text_rect = text_surface.get_rect(center=(screen_width // 2, y_offset))
                self.screen.blit(text_surface, text_rect)
                y_offset += line_height
            
        elif self.is_video and self.video_player:
            frame_surface = self.video_player.get_frame()
            if frame_surface:
                pos = self.video_player.get_position()
                self.screen.blit(frame_surface, pos)
            
            if self.caption:
                self._draw_caption_box()
                    
        elif self.surface:
            img_rect = self.surface.get_rect()
            img_rect.center = (screen_width // 2, screen_height // 2)
            self.screen.blit(self.surface, img_rect)

            if self.caption:
                self._draw_caption_box()
        
        if self.is_urgent:
            urgent_font = pygame.font.SysFont("Calibri", 28, bold=True)
            urgent_text = urgent_font.render("URGENT", True, (255, 50, 50))
            self.screen.blit(urgent_text, (screen_width - 150, 20))
    
    def _draw_caption_box(self):
        """Draw caption box at bottom with emoji support"""
        screen_width, screen_height = self.screen.get_size()
        caption_height = 150
        caption_y = screen_height - caption_height

        gradient_surface = pygame.Surface((screen_width, caption_height), pygame.SRCALPHA)
        steps = 20
        for i in range(steps):
            alpha = int(255 * 0.6 * (i / steps))
            color = (0, 0, 0, alpha)
            step_height = caption_height // steps
            pygame.draw.rect(gradient_surface, color,
                            (0, i * step_height, screen_width, step_height))

        self.screen.blit(gradient_surface, (0, screen_height - caption_height))

        font = load_arabic_font(36)
        text_color = (255, 255, 255)
        max_width = screen_width - 40
        lines = wrap_text(self.caption, font, max_width)

        y_offset = caption_y + 20
        for line in lines[:3]:
            # Render text with emojis
            text_surface = render_text_with_emojis(line, font, text_color)
            self.screen.blit(text_surface, (20, y_offset))
            y_offset += 40
    
    def draw_with_offset(self, offset_ratio=0):
        """Draw slide with drag offset"""
        screen_width, screen_height = self.screen.get_size()
        pixel_offset = int(screen_width * offset_ratio * 1.0)
        pixel_offset = max(-screen_width // 2, min(screen_width // 2, pixel_offset))
        
        self.screen.fill((0, 0, 0))
        
        if self.is_text_only:
            content_font = load_arabic_font(48)
            text_color = (255, 255, 255)
            max_width = screen_width - 100
            lines = wrap_text(self.caption, content_font, max_width)
            line_height = 60
            total_height = len(lines) * line_height
            y_offset = (screen_height - total_height) // 2
            
            for line in lines:
                text_surface = render_text_with_emojis(line, content_font, text_color)
                text_rect = text_surface.get_rect(
                    center=(screen_width // 2 + pixel_offset, y_offset)
                )
                self.screen.blit(text_surface, text_rect)
                y_offset += line_height
        
        elif self.is_video and self.video_player:
            frame_surface = self.video_player.get_frame()
            if frame_surface:
                pos = self.video_player.get_position()
                self.screen.blit(frame_surface, (pos[0] + pixel_offset, pos[1]))
            
            if self.caption:
                self._draw_caption_box()
        
        elif self.surface:
            img_rect = self.surface.get_rect()
            img_rect.center = (screen_width // 2 + pixel_offset, screen_height // 2)
            self.screen.blit(self.surface, img_rect)
            
            if self.caption:
                self._draw_caption_box()
        
        if self.is_urgent:
            urgent_font = pygame.font.SysFont("Calibri", 28, bold=True)
            urgent_text = urgent_font.render("URGENT", True, (255, 50, 50))
            self.screen.blit(urgent_text, (screen_width - 150 + pixel_offset, 20))
    
    def cleanup(self):
        """Release resources"""
        self.stop_video()
        if self.video_player:
            self.video_player.cleanup()


class NavigationBar:
    """Navigation bar with pill indicators"""
    
    def __init__(self, screen, num_slides):
        self.screen = screen
        self.num_slides = num_slides
        self.active_index = 0
        
        self.indicator_width = 40
        self.indicator_height = 20
        self.spacing = 5
        self.padding = 10
        
        indicators_width = (self.indicator_width + self.spacing) * num_slides - self.spacing
        total_width = indicators_width + 2 * self.padding
        
        screen_width, screen_height = screen.get_size()
        max_width = int(screen_width * 0.8)
        
        if total_width > max_width:
            available_width = max_width - 2 * self.padding
            self.indicator_width = min(40, (available_width + self.spacing) // num_slides - self.spacing)
            self.indicator_width = max(15, self.indicator_width)
            if num_slides > 1:
                self.spacing = max(3, (available_width - self.indicator_width * num_slides) // (num_slides - 1))
            self.width = max_width
        else:
            self.width = total_width
        
        self.height = 40
        self.x = (screen_width - self.width) // 2
        self.y = screen_height - 80
    
    def set_active(self, index):
        """Set active indicator"""
        self.active_index = index
    
    def draw(self):
        """Draw navigation bar"""
        bg_rect = (self.x, self.y, self.width, self.height)
        draw_rounded_rect(self.screen, (50, 50, 50, 128), bg_rect, 20)
        
        available_width = self.width - 2 * self.padding
        indicator_y = self.y + (self.height - self.indicator_height) // 2
        total_indicators_width = self.indicator_width * self.num_slides + self.spacing * (self.num_slides - 1)
        start_x = self.x + self.padding + (available_width - total_indicators_width) // 2
        
        for i in range(self.num_slides):
            indicator_x = start_x + i * (self.indicator_width + self.spacing)
            indicator_rect = (indicator_x, indicator_y, self.indicator_width, self.indicator_height)
            
            if i == self.active_index:
                color = (32, 142, 208)
            else:
                color = (128, 128, 128, 128)
            
            radius = self.indicator_height // 2
            draw_rounded_rect(self.screen, color, indicator_rect, radius)


class Notification:
    """Temporary notification overlay"""
    
    def __init__(self, screen, message):
        self.screen = screen
        self.message = message
        self.start_time = pygame.time.get_ticks()
        self.duration = 3000
        self.alpha = 255
    
    def is_active(self):
        """Check if notification is still active"""
        elapsed = pygame.time.get_ticks() - self.start_time
        return elapsed < self.duration
    
    def draw(self):
        """Draw notification"""
        if not self.is_active():
            return
        
        elapsed = pygame.time.get_ticks() - self.start_time
        
        if elapsed > self.duration - 1000:
            self.alpha = int(255 * (self.duration - elapsed) / 1000)
        
        screen_width, screen_height = self.screen.get_size()
        notif_width = 400
        notif_height = 60
        notif_surface = pygame.Surface((notif_width, notif_height), pygame.SRCALPHA)
        
        draw_rounded_rect(notif_surface, (26, 26, 26, int(217 * self.alpha / 255)), 
                         (0, 0, notif_width, notif_height), 15)
        
        font = pygame.font.Font(None, 32)
        text_surface = render_text_with_emojis(self.message, font, (255, 255, 255, self.alpha))
        text_rect = text_surface.get_rect(center=(notif_width // 2, notif_height // 2))
        notif_surface.blit(text_surface, text_rect)
        
        notif_x = (screen_width - notif_width) // 2
        notif_y = 50
        
        self.screen.blit(notif_surface, (notif_x, notif_y))


class ThelabApp:
    """Main application"""
    
    def __init__(self):
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.display.set_caption("The Lab Media Carousel")
        
        self.clock = pygame.time.Clock()
        self.running = True
        
        self.voice_manager = VoiceManager(URGENT_VOICE_FILE)
        
        posts = load_posts()
        urgent = [p for p in posts if p.get("urgent")]
        
        self.slides_data = urgent if urgent else (posts if posts else [
            {"media": "", "caption": "Your ads here", "is_video": False, "is_text_only": True}
        ])
        
        self.slides = []
        self.current_index = 0
        
        for i, slide_data in enumerate(self.slides_data):
            slide = MediaSlide(
                self.screen,
                slide_data["media"],
                slide_data.get("caption", ""),
                slide_data.get("is_video", False),
                slide_index=i,
                is_urgent=slide_data.get("urgent", False),
                timestamp=slide_data.get("timestamp"),
                is_text_only=slide_data.get("is_text_only", False)
            )
            self.slides.append(slide)
            
            if slide_data.get("urgent") and slide_data.get("timestamp"):
                self.voice_manager.register_urgent_ad(slide_data["timestamp"])
        
        self.nav = NavigationBar(self.screen, len(self.slides))
        
        self.mode = "auto"
        self.gesture = GestureControl(show_display=False, callback=self.on_gesture)
        
        self.last_auto_scroll = pygame.time.get_ticks()
        self.last_refresh = pygame.time.get_ticks()
        self.last_voice_check = pygame.time.get_ticks()
        self.auto_scroll_interval = 10000
        self.refresh_interval = 10000
        self.voice_check_interval = 30000
        
        self.notifications = []
        
        if self.slides:
            self.start_current_slide()
        
        self.last_fingerprint = None
        self.check_and_play_urgent_voices()
    
    def start_current_slide(self):
        """Start playing current slide and show first frame immediately"""
        if not self.slides:
            return

        for slide in self.slides:
            slide.stop_video()

        self.screen.fill((0, 0, 0))

        slide = self.slides[self.current_index]

        if slide.is_video:
            slide.play_video()
            # FORCE first frame render
            frame = slide.video_player.get_frame()
            if frame:
                pos = slide.video_player.get_position()
                self.screen.blit(frame, pos)
                if slide.caption:
                    slide._draw_caption_box()  # draw caption too

        self.nav.set_active(self.current_index)
        pygame.display.flip()  # show it NOW

        # Reset timer AFTER display
        self.last_auto_scroll = pygame.time.get_ticks()
    
    def check_and_play_urgent_voices(self):
        """Check all urgent ads and play voice if scheduled"""
        for slide in self.slides:
            if slide.is_urgent and slide.timestamp:
                if self.voice_manager.should_play_voice(slide.timestamp):
                    self.voice_manager.play_voice()
                    self.voice_manager.mark_played(slide.timestamp)
    
    def next_slide(self):
        """Go to next slide"""
        self.current_index = (self.current_index + 1) % len(self.slides)
        self.start_current_slide()
    
    def previous_slide(self):
        """Go to previous slide"""
        self.current_index = (self.current_index - 1) % len(self.slides)
        self.start_current_slide()
    
    def show_notification(self, message):
        """Show notification"""
        notif = Notification(self.screen, message)
        self.notifications.append(notif)
    
    def on_gesture(self, event):
        """Handle gesture events - Palm presence controls the mode"""
        event_type = event.get("type")
        
        if not hasattr(self, 'gesture_state'):
            self.gesture_state = {
                'dragging': False,
                'drag_offset': 0,
                'slide_changed': False,
                'locked': False
            }
        
        # PALM APPEARED - Switch to gesture control mode
        if event_type == "palm_appeared":
            self.mode = "gesture"
            self.show_notification("🖐️ Gesture Control")
            print("✅ Palm detected - Gesture control ACTIVE")
            return
        
        # PALM DISAPPEARED or HAND LOST - Switch to auto-scroll mode
        elif event_type in ["palm_disappeared", "hand_lost"]:
            self.mode = "auto"
            self.show_notification("Auto-scroll")
            print("✅ Palm gone - Auto-scroll ACTIVE")
            
            # Reset gesture state
            self.gesture_state['dragging'] = False
            self.gesture_state['drag_offset'] = 0
            self.gesture_state['slide_changed'] = False
            self.gesture_state['locked'] = False
            
            # Restart auto-scroll timer
            self.last_auto_scroll = pygame.time.get_ticks()
            return
        
        # Only process pinch gestures if in gesture mode
        if self.mode != "gesture":
            return
        
        # PINCH START
        if event_type == "pinch_start":
            # Don't allow new pinch if locked (after slide change)
            if self.gesture_state.get('locked', False):
                return
            
            self.gesture_state['dragging'] = True
            self.gesture_state['drag_offset'] = 0
            self.gesture_state['slide_changed'] = False
            self.gesture_state['locked'] = False
            self.show_notification("👆 Pinched")
            return
        
        # PINCH DRAG
        elif event_type == "pinch_drag":
            # Ignore drag if locked or not dragging
            if self.gesture_state.get('locked', False) or not self.gesture_state['dragging']:
                return
            
            offset = event.get("offset", 0)
            self.gesture_state['drag_offset'] = offset
            
            threshold = 0.15  # Swipe threshold
            
            if not self.gesture_state['slide_changed']:
                if offset > threshold:
                    # Swipe RIGHT = Previous slide
                    self.previous_slide()
                    self.gesture_state['slide_changed'] = True
                    self.gesture_state['locked'] = True
                    self.gesture_state['drag_offset'] = 0
                    self.show_notification("← Previous")
                    
                elif offset < -threshold:
                    # Swipe LEFT = Next slide
                    self.next_slide()
                    self.gesture_state['slide_changed'] = True
                    self.gesture_state['locked'] = True
                    self.gesture_state['drag_offset'] = 0
                    self.show_notification("Next →")
            
            return
        
        # PINCH RELEASE
        elif event_type == "pinch_release":
            # Reset gesture state
            self.gesture_state['dragging'] = False
            self.gesture_state['drag_offset'] = 0
            self.gesture_state['slide_changed'] = False
            self.gesture_state['locked'] = False
            self.show_notification("✋ Released")
            return
        
        # Optional: Handle fast movement for future features
        elif event_type == "fast_movement_start":
            # Could trigger special animations or effects
            pass
        
        elif event_type == "fast_movement_end":
            # Clean up fast movement state
            pass
    
    def refresh_posts(self):
        """Refresh posts and rebuild if changed"""
        posts = load_posts()
        new_fp = [(p["media"], p["caption"], p.get("urgent", False)) for p in posts]
        
        if self.last_fingerprint == new_fp:
            return
        
        self.last_fingerprint = new_fp
        
        for slide in self.slides:
            slide.cleanup()
        
        urgent = [p for p in posts if p.get("urgent")]
        self.slides_data = urgent if urgent else (posts if posts else [
            {"media": "", "caption": "Your ads here ", "is_video": False, "is_text_only": True}
        ])
        
        self.slides = []
        
        for i, slide_data in enumerate(self.slides_data):
            slide = MediaSlide(
                self.screen,
                slide_data["media"],
                slide_data.get("caption", ""),
                slide_data.get("is_video", False),
                slide_index=i,
                is_urgent=slide_data.get("urgent", False),
                timestamp=slide_data.get("timestamp"),
                is_text_only=slide_data.get("is_text_only", False)
            )
            self.slides.append(slide)
            
            if slide_data.get("urgent") and slide_data.get("timestamp"):
                self.voice_manager.register_urgent_ad(slide_data["timestamp"])
        
        self.nav = NavigationBar(self.screen, len(self.slides))
        
        self.current_index = 0
        if self.slides:
            self.start_current_slide()
    
    def run(self):
        """Main game loop"""
        while self.running:
            current_time = pygame.time.get_ticks()
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif event.key == pygame.K_LEFT:
                        self.previous_slide()
                    elif event.key == pygame.K_RIGHT:
                        self.next_slide()
            
            try:
                self.gesture.run_once()
            except Exception as e:
                pass
            
            if current_time - self.last_voice_check > self.voice_check_interval:
                self.check_and_play_urgent_voices()
                self.voice_manager.cleanup_expired()
                self.last_voice_check = current_time
            
            current_slide = self.slides[self.current_index]
            if current_slide.is_video_finished():
                self.next_slide()
            
            if self.mode == "auto" and not current_slide.is_video:
                if current_time - self.last_auto_scroll > self.auto_scroll_interval:
                    self.next_slide()
            
            if current_time - self.last_refresh > self.refresh_interval:
                self.refresh_posts()
                self.last_refresh = current_time
            
            if self.slides:
                if (hasattr(self, 'gesture_state') and 
                    self.gesture_state.get('dragging', False) and 
                    abs(self.gesture_state.get('drag_offset', 0)) > 0.01):
                    self.slides[self.current_index].draw_with_offset(
                        self.gesture_state['drag_offset']
                    )
                else:
                    self.slides[self.current_index].draw()
            
            self.nav.draw()
            
            self.notifications = [n for n in self.notifications if n.is_active()]
            for notif in self.notifications:
                notif.draw()
            
            pygame.display.flip()
            self.clock.tick(60)
        
        pygame.mixer.music.stop()
        for slide in self.slides:
            slide.cleanup()
        pygame.quit()


# if __name__ == '__main__':
#     app = ThelabApp()
#     app.run()