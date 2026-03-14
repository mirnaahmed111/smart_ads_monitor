import cv2
import mediapipe as mp
import math
import time
from collections import deque

class GestureControl:
    def __init__(self, camera_index=0, show_display=False, callback=None):
        self.mp_hands = mp.solutions.hands
        self.mp_draw = mp.solutions.drawing_utils
        self.cap = cv2.VideoCapture(camera_index)
        self.hands = self.mp_hands.Hands(
            max_num_hands=1, 
            min_detection_confidence=0.4,  # Lower = faster detection
            min_tracking_confidence=0.4,    # Lower = faster tracking
            model_complexity=0              # Lighter model = faster processing
        )
        self.show_display = show_display
        self.callback = callback
        
        # Pinch tracking
        self.is_pinching = False
        self.pinch_start_x = None
        self.current_x = None
        self.last_callback_time = 0
        
        # Palm detection for mode control
        self.palm_detected = False
        self.last_palm_state = False
        
        # Fast movement tracking
        self.position_history = deque(maxlen=5)   # Last 5 frames (reduced)
        self.velocity_history = deque(maxlen=3)   # Last 3 velocities (reduced)
        self.last_position = None
        self.last_time = None
        self.is_moving_fast = False
        
        # Thresholds for fast movement (more aggressive)
        self.fast_velocity_threshold = 1.2  # Lower threshold = easier to trigger
        self.fast_movement_duration = 2  # Only 2 frames needed (faster response)
    
    def dist(self, p1, p2):
        """Calculate distance between two points"""
        return math.hypot(p1.x - p2.x, p1.y - p2.y)
    
    def get_hand_size(self, lm):
        """Calculate hand size (wrist to middle finger tip) for normalization"""
        wrist = lm[0]
        middle_tip = lm[12]
        return self.dist(wrist, middle_tip)
    
    def detect_pinch(self, lm):
        """Detect pinch gesture - thumb tip close to index tip (adaptive threshold)"""
        thumb_tip = lm[4]
        index_tip = lm[8]
        
        # Calculate distance between thumb and index tips
        pinch_distance = self.dist(thumb_tip, index_tip)
        
        # Get hand size for normalization
        hand_size = self.get_hand_size(lm)
        
        # Adaptive threshold: pinch distance relative to hand size
        normalized_distance = pinch_distance / hand_size if hand_size > 0 else 1.0
        
        # Very tight threshold for actual touch
        return normalized_distance < 0.15
    
    def is_palm(self, lm):
        """Detect open palm - at least 3 fingers extended"""
        # Finger tips
        tips = [8, 12, 16, 20]  # index, middle, ring, pinky
        palm = lm[0]  # wrist
        
        # Count extended fingers
        extended = 0
        for tip in tips:
            distance = self.dist(lm[tip], palm)
            if distance > 0.15:
                extended += 1
        
        return extended >= 3  # At least 3 fingers extended
    
    def calculate_velocity(self, current_pos, current_time):
        """Calculate hand movement velocity"""
        if self.last_position is None or self.last_time is None:
            self.last_position = current_pos
            self.last_time = current_time
            return 0.0
        
        # Calculate distance moved
        dx = current_pos['x'] - self.last_position['x']
        dy = current_pos['y'] - self.last_position['y']
        distance = math.sqrt(dx**2 + dy**2)
        
        # Calculate time delta
        dt = current_time - self.last_time
        
        # Calculate velocity (distance per second)
        velocity = distance / dt if dt > 0 else 0.0
        
        # Update last position and time
        self.last_position = current_pos
        self.last_time = current_time
        
        return velocity
    
    def detect_fast_movement(self, velocity):
        """Detect if movement is fast based on velocity history"""
        self.velocity_history.append(velocity)
        
        # Immediate response - check if current velocity is high
        if velocity > self.fast_velocity_threshold * 1.5:  # Instant trigger for very fast
            return True
        
        # Need enough samples for normal fast detection
        if len(self.velocity_history) < self.fast_movement_duration:
            return velocity > self.fast_velocity_threshold  # Use current velocity
        
        # Check if recent velocities exceed threshold
        fast_frames = sum(1 for v in list(self.velocity_history)[-self.fast_movement_duration:] 
                         if v > self.fast_velocity_threshold)
        
        return fast_frames >= self.fast_movement_duration
    
    def run_once(self):
        """Process single frame - Meta Quest style"""
        ret, frame = self.cap.read()
        if not ret:
            return
        
        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape
        
        # Resize frame for faster processing (optional but recommended)
        frame_small = cv2.resize(frame, (640, 480))  # Smaller = faster
        rgb = cv2.cvtColor(frame_small, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb)
        
        current_time = time.time()
        
        if results.multi_hand_landmarks:
            hand_landmarks = results.multi_hand_landmarks[0]
            lm = hand_landmarks.landmark
            
            # Get hand center position (normalized 0-1)
            hand_center_x = lm[9].x
            hand_center_y = lm[9].y
            current_pos = {'x': hand_center_x, 'y': hand_center_y}
            
            # Calculate velocity
            velocity = self.calculate_velocity(current_pos, current_time)
            
            # Detect fast movement
            is_fast_now = self.detect_fast_movement(velocity)
            
            # Trigger fast movement callback
            if is_fast_now and not self.is_moving_fast:
                self.is_moving_fast = True
                if self.callback:
                    self.callback({
                        "type": "fast_movement_start",
                        "velocity": velocity,
                        "x": hand_center_x,
                        "y": hand_center_y
                    })
            elif not is_fast_now and self.is_moving_fast:
                self.is_moving_fast = False
                if self.callback:
                    self.callback({
                        "type": "fast_movement_end",
                        "x": hand_center_x,
                        "y": hand_center_y
                    })
            
            # Detect pinch
            pinching_now = self.detect_pinch(lm)
            
            # Detect open palm
            palm_detected_now = self.is_palm(lm)
            
            # Check if palm state changed
            if palm_detected_now != self.last_palm_state:
                self.last_palm_state = palm_detected_now
                
                if palm_detected_now:
                    # Palm appeared - switch to gesture control
                    self.palm_detected = True
                    if self.callback:
                        self.callback({
                            "type": "palm_appeared",
                            "x": hand_center_x,
                            "y": hand_center_y
                        })
                else:
                    # Palm disappeared - switch to auto mode
                    self.palm_detected = False
                    if self.callback:
                        self.callback({
                            "type": "palm_disappeared",
                            "x": hand_center_x,
                            "y": hand_center_y
                        })
            
            # Update palm state
            self.palm_detected = palm_detected_now
            
            # Draw hand landmarks if display enabled
            if self.show_display:
                self.mp_draw.draw_landmarks(
                    frame, 
                    hand_landmarks, 
                    self.mp_hands.HAND_CONNECTIONS
                )
            
            # STATE: Starting pinch
            if pinching_now and not self.is_pinching:
                self.is_pinching = True
                self.pinch_start_x = hand_center_x
                self.current_x = hand_center_x
                
                if self.callback:
                    self.callback({
                        "type": "pinch_start",
                        "x": hand_center_x,
                        "is_moving_fast": self.is_moving_fast
                    })
                self.last_callback_time = current_time
            
            # STATE: Maintaining pinch and moving
            elif pinching_now and self.is_pinching:
                self.current_x = hand_center_x
                
                # Calculate offset from pinch start
                offset = hand_center_x - self.pinch_start_x
                
                # Send continuous updates (throttled to ~60fps)
                if current_time - self.last_callback_time > 0.016:  # ~60fps
                    if self.callback:
                        self.callback({
                            "type": "pinch_drag",
                            "x": hand_center_x,
                            "offset": offset,
                            "start_x": self.pinch_start_x,
                            "velocity": velocity,
                            "is_moving_fast": self.is_moving_fast
                        })
                    self.last_callback_time = current_time
            
            # STATE: Released pinch
            elif not pinching_now and self.is_pinching:
                final_offset = self.current_x - self.pinch_start_x if self.current_x else 0
                
                if self.callback:
                    self.callback({
                        "type": "pinch_release",
                        "final_offset": final_offset,
                        "x": hand_center_x,
                        "was_moving_fast": self.is_moving_fast
                    })
                
                # Reset state
                self.is_pinching = False
                self.pinch_start_x = None
                self.current_x = None
        
        else:
            # No hand detected
            if self.is_pinching:
                # Force release
                if self.callback:
                    self.callback({
                        "type": "pinch_release",
                        "final_offset": 0,
                        "x": 0.5
                    })
                
                self.is_pinching = False
                self.pinch_start_x = None
                self.current_x = None
            
            # Hand disappeared - notify if palm was detected
            if self.palm_detected:
                self.palm_detected = False
                self.last_palm_state = False
                if self.callback:
                    self.callback({
                        "type": "hand_lost",
                        "x": 0.5,
                        "y": 0.5
                    })
            
            # Reset fast movement tracking
            if self.is_moving_fast:
                self.is_moving_fast = False
                if self.callback:
                    self.callback({
                        "type": "fast_movement_end",
                        "x": 0.5,
                        "y": 0.5
                    })
            
            self.last_position = None
            self.last_time = None
            self.velocity_history.clear()
        
        if self.show_display:
            # Draw pinch indicator
            if self.is_pinching:
                cv2.putText(frame, "PINCHING", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            
            # Draw palm/mode indicator
            if self.palm_detected:
                cv2.putText(frame, "GESTURE MODE", (10, 70), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
            else:
                cv2.putText(frame, "AUTO MODE", (10, 70), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (128, 128, 128), 2)
            
            # Draw fast movement indicator
            if self.is_moving_fast:
                cv2.putText(frame, "FAST MOVEMENT!", (10, 110), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            
            # Draw velocity
            if len(self.velocity_history) > 0:
                velocity_text = f"Velocity: {self.velocity_history[-1]:.2f}"
                cv2.putText(frame, velocity_text, (10, 150), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            cv2.imshow("Gesture Control", frame)
            cv2.waitKey(1)
    
    def cleanup(self):
        """Release resources"""
        self.cap.release()
        if self.show_display:
            cv2.destroyAllWindows()


# Example usage
# if __name__ == "__main__":
#     def handle_gesture(data):
#         """Callback to handle gesture events"""
#         event_type = data.get("type")
        
#         if event_type == "palm_appeared":
#             print("🖐️  PALM DETECTED - Gesture control ACTIVE")
        
#         elif event_type == "palm_disappeared":
#             print("👋 PALM GONE - Auto-scroll ACTIVE")
        
#         elif event_type == "hand_lost":
#             print("❌ Hand lost - Auto-scroll ACTIVE")
        
#         elif event_type == "fast_movement_start":
#             print(f"🚀 FAST MOVEMENT DETECTED! Velocity: {data.get('velocity', 0):.2f}")
        
#         elif event_type == "fast_movement_end":
#             print("🛑 Fast movement ended")
        
#         elif event_type == "pinch_start":
#             fast_status = "FAST" if data.get("is_moving_fast") else "normal"
#             print(f"👌 Pinch started at x={data.get('x', 0):.2f} ({fast_status})")
        
#         elif event_type == "pinch_drag":
#             if data.get("is_moving_fast"):
#                 print(f"⚡ FAST pinch drag: offset={data.get('offset', 0):.2f}, velocity={data.get('velocity', 0):.2f}")
        
#         elif event_type == "pinch_release":
#             fast_status = "FAST" if data.get("was_moving_fast") else "normal"
#             print(f"✋ Pinch released ({fast_status}): offset={data.get('final_offset', 0):.2f}")
    
#     # Initialize gesture control
#     gc = GestureControl(
#         camera_index=0,
#         show_display=True,
#         callback=handle_gesture
#     )
    
#     print("Gesture Control with Palm Detection")
#     print("=" * 50)
#     print("🖐️  Show PALM (3+ fingers) → Gesture control mode")
#     print("👋 Hide palm → Auto-scroll mode")
#     print("👌 PINCH (thumb + index) and drag to navigate (when palm visible)")
#     print("🚀 Move quickly to trigger fast movement detection")
#     print("Press 'q' to quit")
#     print()
    
#     try:
#         while True:
#             gc.run_once()
            
#             # Check for quit
#             if cv2.waitKey(1) & 0xFF == ord('q'):
#                 break
    
#     finally:
#         gc.cleanup()
#         print("\nGesture control stopped")