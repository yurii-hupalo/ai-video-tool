import streamlit as st
import fal_client
import openai
import os
import requests
import json
import subprocess

# Спроба імпорту mutagen
try:
    from mutagen.mp3 import MP3
except ImportError:
    st.error("🚨 Бібліотека `mutagen` не встановлена. Введи: pip install mutagen")
    MP3 = None

# --- НАЛАШТУВАННЯ ---
st.set_page_config(page_title="AI Mega Studio", page_icon="🎛️", layout="wide")

# ==========================================
# 1. СИСТЕМНІ ФУНКЦІЇ
# ==========================================

def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except FileNotFoundError:
        return False

def save_file(url, filename):
    try:
        r = requests.get(url)
        with open(filename, 'wb') as f: f.write(r.content)
        return filename
    except Exception as e:
        st.error(f"Save Error: {e}")
        return None

def get_audio_duration(filename):
    if MP3 is None: return 5
    try:
        audio = MP3(filename)
        return audio.info.length
    except Exception:
        return 5

# --- ГЕНЕРАЦІЯ АУДІО ---
def generate_voiceover(text, voice_name, filename):
    try:
        client = openai.OpenAI()
        response = client.audio.speech.create(
            model="tts-1",
            voice=voice_name,
            input=text
        )
        response.stream_to_file(filename)
        return filename
    except Exception as e:
        st.error(f"TTS Error: {e}")
        return None

def generate_subtitles(audio_path):
    try:
        client = openai.OpenAI()
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", file=audio_file, response_format="srt"
            )
        srt_filename = "subtitles.srt"
        with open(srt_filename, "w") as f:
            f.write(transcript)
        return os.path.abspath(srt_filename)
    except Exception as e:
        st.warning(f"Subs Error: {e}")
        return None

# --- ОБРОБКА ВІДЕО ---

def normalize_visual(input_path, output_path, duration, width, height):
    input_abs = os.path.abspath(input_path)
    output_abs = os.path.abspath(output_path)
    scale = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    
    if input_path.endswith(".jpg") or input_path.endswith(".png"):
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", input_abs,
            "-vf", f"{scale},format=yuv420p",
            "-c:v", "libx264", "-t", str(duration), "-pix_fmt", "yuv420p", "-r", "25",
            output_abs
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-i", input_abs,
            "-vf", f"{scale},fps=25,format=yuv420p",
            "-c:v", "libx264", "-t", str(duration), "-pix_fmt", "yuv420p",
            output_abs
        ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_abs

def assemble_final_video(clips, music_path, voice_path, sub_path, output_path):
    list_file = os.path.abspath("clips.txt")
    with open(list_file, "w") as f:
        for clip in clips:
            f.write(f"file '{clip}'\n")
    
    abs_music = os.path.abspath(music_path)
    abs_voice = os.path.abspath(voice_path) if voice_path else None
    
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file]
    cmd += ["-stream_loop", "-1", "-i", abs_music]
    
    filter_complex = ""
    if abs_voice:
        cmd += ["-i", abs_voice]
        filter_complex = "[1:a]volume=0.1[bg];[2:a]volume=1.3[speech];[bg][speech]amix=inputs=2:duration=first[a_out]"
    else:
        filter_complex = "[1:a]volume=1.0[a_out]"

    video_filter = "null"
    if sub_path:
        sub_escaped = sub_path.replace("\\", "/").replace(":", "\\:")
        video_filter = f"subtitles='{sub_escaped}':force_style='Fontsize=18,PrimaryColour=&Hffffff,OutlineColour=&H000000,BorderStyle=1,Outline=1,Shadow=0,Alignment=2,MarginV=50'"

    cmd += [
        "-filter_complex", f"{filter_complex};[0:v]{video_filter}[v_out]",
        "-map", "[v_out]", "-map", "[a_out]",
        "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k", "-shortest",
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return output_path
    except subprocess.CalledProcessError as e:
        st.error(f"FFmpeg Error: {e}")
        return None

# ==========================================
# 2. ІНТЕРФЕЙС (SIDEBAR)
# ==========================================
with st.sidebar:
    st.title("🎛️ AI Mega Studio")
    
    openai_key = st.text_input("OpenAI Key", type="password", value="[АПІ КЛЮЧ ОПЕНАІ]")
    fal_key = st.text_input("Fal.ai Key", type="password", value="[АПІ КЛЮЧ ФАЛ АІ]")
    
    st.markdown("---")
    
    # ЗМІНЕНО ПОРЯДОК: Story Mode тепер перший (дефолтний)
    MODE = st.selectbox("Обери режим:", [
        "📜 Story Mode (Slideshow)", 
        "🚀 Hybrid Pro (Video+Img+Subs)",
        "🎬 Quick Loop (Kling)"
    ])
    
    st.markdown("---")
    format_opt = st.radio("Формат:", ("9:16 (TikTok)", "16:9 (YouTube)"))
    if "9:16" in format_opt:
        W, H = 720, 1280
        fal_size = "portrait_16_9"
    else:
        W, H = 1280, 720
        fal_size = "landscape_16_9"
        
    st.markdown("### 🎵 Налаштування")
    voice_opt = st.selectbox("Голос:", ["onyx", "alloy", "echo", "shimmer", "nova", "fable"])
    uploaded_music = st.file_uploader("Фонова музика (mp3)", type=["mp3"])
    add_subs = st.checkbox("Додати субтитри", value=True)
    
    # --- ВИПРАВЛЕНО: Слайдер тепер завжди тут ---
    st.markdown("### 📝 Кількість Сцен")
    num_scenes = st.slider("Обери кількість:", 1, 20, 5)
    
    if MODE == "🎬 Quick Loop (Kling)":
        st.info("ℹ️ Для Quick Loop буде використана лише 1 сцена, незалежно від слайдера.")
        real_num_scenes = 1
    else:
        real_num_scenes = num_scenes

# ==========================================
# 3. ЛОГІКА ПРОГРАМИ
# ==========================================

st.title(f"{MODE}")

if not check_ffmpeg():
    st.error("🚨 Немає FFmpeg!")
    st.stop()
    
if "[АПІ" in openai_key:
    st.warning("Встав ключі!")
    st.stop()

os.environ["OPENAI_API_KEY"] = openai_key
os.environ["FAL_KEY"] = fal_key

topic = st.text_input("Тема твого відео:", "The history of coffee")

if st.button("🚀 ПОЧАТИ ГЕНЕРАЦІЮ"):
    
    with st.status("🏗️ Працюю...", expanded=True) as status:
        
        # --- ЕТАП 1: СЦЕНАРІЙ ---
        st.write("📝 1. Сценарій...")
        client = openai.OpenAI()
        
        if MODE == "🎬 Quick Loop (Kling)":
            prompt = f"Create a looping video concept for '{topic}'. JSON: {{'visual_prompt': 'desc', 'music_mood': 'desc'}}"
        
        elif MODE == "📜 Story Mode (Slideshow)":
            prompt = f"Create a documentary script for '{topic}' with {real_num_scenes} scenes. JSON: {{'scenes': ['img1', 'img2'...], 'narration': 'text', 'music_mood': 'desc'}}"
            
        elif MODE == "🚀 Hybrid Pro (Video+Img+Subs)":
            prompt = f"""
            Create a hybrid video script for '{topic}' with {real_num_scenes} scenes. 
            Use 'video' type only for high action, 'image' for static.
            JSON: {{
                "narration": "text", 
                "music_mood": "desc",
                "scenes": [
                    {{'type': 'image', 'prompt': '... '}},
                    {{'type': 'video', 'prompt': '... '}}
                ]
            }}
            """
            
        resp = client.chat.completions.create(model="gpt-4o", messages=[{"role":"user", "content": prompt}], response_format={"type": "json_object"})
        data = json.loads(resp.choices[0].message.content)
        
        # --- ЕТАП 2: АУДІО ---
        st.write("🎙️ 2. Аудіо...")
        voice_path = None
        voice_dur = 5
        if 'narration' in data:
            voice_path = generate_voiceover(data['narration'], voice_opt, "voice.mp3")
            voice_dur = get_audio_duration(voice_path)
        
        music_path = "music.mp3"
        if uploaded_music:
            with open(music_path, "wb") as f: f.write(uploaded_music.getbuffer())
        else:
            music_len = 15 if MODE == "🎬 Quick Loop (Kling)" else min(int(voice_dur + 5), 45)
            try:
                h_mus = fal_client.submit("fal-ai/stable-audio", arguments={"prompt": data['music_mood'], "seconds_total": music_len})
                save_file(h_mus.get()['audio_file']['url'], music_path)
            except:
                st.warning("Музика не вийшла.")

        sub_path = None
        if add_subs and voice_path:
            st.write("📝 Субтитри...")
            sub_path = generate_subtitles(voice_path)

        # --- ЕТАП 3: ВІЗУАЛ ---
        st.write(f"🎨 3. Візуал ({real_num_scenes} сцен)...")
        clips = []
        
        if MODE == "🎬 Quick Loop (Kling)":
            h_img = fal_client.submit("fal-ai/flux-pro", arguments={"prompt": data['visual_prompt'], "image_size": fal_size})
            img_url = h_img.get()['images'][0]['url']
            h_vid = fal_client.submit("fal-ai/kling-video/v1/standard/image-to-video", arguments={"prompt": data['visual_prompt'], "image_url": img_url, "duration": "5"})
            vid_path = save_file(h_vid.get()['video']['url'], "raw_kling.mp4")
            clips.append(normalize_visual(vid_path, "clip_0.mp4", 10, W, H))
            
        elif MODE == "📜 Story Mode (Slideshow)":
            time_per_slide = voice_dur / len(data['scenes'])
            prog = st.progress(0)
            for i, p in enumerate(data['scenes']):
                try:
                    h = fal_client.submit("fal-ai/recraft-v3", arguments={"prompt": p, "image_size": fal_size, "style": "realistic_image"})
                    img_path = save_file(h.get()['images'][0]['url'], f"raw_{i}.jpg")
                    clips.append(normalize_visual(img_path, f"clip_{i}.mp4", time_per_slide, W, H))
                    prog.progress((i+1)/len(data['scenes']))
                except Exception as e:
                    st.warning(f"Error scene {i}: {e}")
                
        elif MODE == "🚀 Hybrid Pro (Video+Img+Subs)":
            time_per_scene = voice_dur / len(data['scenes'])
            prog = st.progress(0)
            for i, scene in enumerate(data['scenes']):
                prompt = scene['prompt']
                try:
                    if scene['type'] == 'video':
                        h_img = fal_client.submit("fal-ai/flux-pro", arguments={"prompt": prompt, "image_size": fal_size})
                        img_url = h_img.get()['images'][0]['url']
                        h_vid = fal_client.submit("fal-ai/kling-video/v1/standard/image-to-video", arguments={"prompt": prompt, "image_url": img_url, "duration": "5"})
                        raw = save_file(h_vid.get()['video']['url'], f"raw_{i}.mp4")
                    else:
                        h_img = fal_client.submit("fal-ai/recraft-v3", arguments={"prompt": prompt, "image_size": fal_size, "style": "realistic_image"})
                        raw = save_file(h_img.get()['images'][0]['url'], f"raw_{i}.jpg")
                    
                    clips.append(normalize_visual(raw, f"clip_{i}.mp4", time_per_scene, W, H))
                    prog.progress((i+1)/len(data['scenes']))
                except Exception as e:
                    st.warning(f"Error scene {i}: {e}")

        # --- ЕТАП 4: МОНТАЖ ---
        st.write("🎬 4. Фінальна збірка...")
        final_file = "RESULT.mp4"
        res = assemble_final_video(clips, music_path, voice_path, sub_path, final_file)
        
        status.update(label="✅ ГОТОВО!", state="complete")

    if res:
        st.balloons()
        st.success(f"Режим: {MODE} | Формат: {format_opt}")
        st.video(res)
        with open(res, "rb") as f:
            st.download_button("⬇️ Скачати", f, "ai_result.mp4")