from flask import Flask, render_template, request, redirect, url_for, jsonify
import os, json, shutil
from datetime import datetime

app = Flask(__name__)

# === زيادة الحد إلى 5 جيجابايت ===
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024 * 1024  # 5 GB

# Upload folder
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# JSON files
LATEST_FILE = 'posts.json'
HISTORY_FILE = 'posts_history.json'

# Initialize files
for file in [LATEST_FILE, HISTORY_FILE]:
    if not os.path.exists(file):
        with open(file, 'w') as f:
            json.dump([], f)

# Allowed extensions
ALLOWED_IMG = {'png', 'jpg', 'jpeg', 'gif','heic'}
ALLOWED_VID = {'mp4', 'avi', 'mov', 'webm', 'mkv'}

def allowed_file(filename, allowed):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed

def save_latest(post_data):
    with open(LATEST_FILE, 'w') as f:
        json.dump([post_data], f, indent=4)

def append_history(post_data):
    with open(HISTORY_FILE, 'r+') as f:
        data = json.load(f)
        data.append(post_data)
        f.seek(0)
        f.truncate()
        json.dump(data, f, indent=4)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        priority = request.form.get('priority', 'ordinary')
        text_content = request.form.get('text_content', '').strip()
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        post_folder = os.path.join(UPLOAD_FOLDER, f"post_{timestamp}")
        os.makedirs(post_folder, exist_ok=True)

        # Save text
        if text_content:
            with open(os.path.join(post_folder, "post.txt"), 'w', encoding='utf-8') as f:
                f.write(f"[{priority.upper()}] {text_content}")

        # Get files
        image = request.files.get('image')
        video = request.files.get('video')

        if image and video:
            return "اختر صورة أو فيديو، ليس كلاهما.", 400

        media_path = None

        # === حفظ الصورة/الفيديو بـ Streaming (آمن للملفات الكبيرة) ===
        if image and allowed_file(image.filename, ALLOWED_IMG):
            # الصور عادة صغيرة → استخدم save مباشرة
            filename = f"image_{image.filename}"
            filepath = os.path.join(post_folder, filename)
            image.save(filepath)  # أسرع وأكثر أماناً للصور
            media_path = f"uploads/post_{timestamp}/{filename}"

        elif video and allowed_file(video.filename, ALLOWED_VID):
            filename = f"video_{video.filename}"
            filepath = os.path.join(post_folder, filename)
            with open(filepath, 'wb') as f:
                while True:
                    chunk = video.stream.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
            media_path = f"uploads/post_{timestamp}/{filename}"

        # Build post entry
        post_entry = {
            "status": priority,
            "text": text_content,
            "media_path": media_path,
            "timestamp": timestamp
        }

        save_latest(post_entry)
        append_history(post_entry)
        return redirect(url_for('index'))

    # === عرض المنشورات ===
    posts = []
    for post in sorted(os.listdir(UPLOAD_FOLDER), reverse=True):
        post_path = os.path.join(UPLOAD_FOLDER, post)
        if not os.path.isdir(post_path):
            continue
        post_data = {"name": post, "text": None, "images": [], "videos": []}
        txt_file = os.path.join(post_path, "post.txt")
        if os.path.exists(txt_file):
            with open(txt_file, encoding='utf-8') as f:
                post_data["text"] = f.read()
        for file in os.listdir(post_path):
            fpath = f"uploads/{post}/{file}"
            if file.lower().endswith(tuple(ALLOWED_IMG)):
                post_data["images"].append(fpath)
            elif file.lower().endswith(tuple(ALLOWED_VID)):
                post_data["videos"].append(fpath)
        posts.append(post_data)

    return render_template('index.html', posts=posts)

@app.route('/delete/<post_name>', methods=['POST'])
def delete_post(post_name):
    post_folder = os.path.join(UPLOAD_FOLDER, post_name)
    if os.path.exists(post_folder):
        shutil.rmtree(post_folder)

    timestamp = post_name.replace("post_", "")

    # حذف من JSON
    for json_file in [HISTORY_FILE, LATEST_FILE]:
        if os.path.exists(json_file):
            with open(json_file, 'r+') as f:
                data = json.load(f)
                new_data = [p for p in data if p.get("timestamp") != timestamp]
                f.seek(0)
                f.truncate()
                json.dump(new_data, f, indent=4)

    return redirect(url_for('index'))

# === للإنتاج: لا تستخدم debug ===
# if __name__ == '__main__':
#     app.run(host='0.0.0.0', port=5000)