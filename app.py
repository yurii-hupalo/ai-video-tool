import streamlit as st
import requests
import json
import os
import subprocess
import time

# Спроба імпорту mutagen
try:
    from mutagen.mp3 import MP3
except ImportError:
    st.error("🚨 Встанови: pip install mutagen")
    MP3 = None

st.set_page_config(page_title="Grok All-in-One Studio", page_icon="🌌", layout="wide")

# ==========================================
# 1. FUNCS: ПРЯМА РОБОТА З xAI API
# ==========================================

def xai_chat_completion(api_key, prompt, model="grok-beta"):
    """Генерація тексту (Сценарій)"""
    url = "https://api.x.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "messages": [
            {"role": "system", "content": "You are a creative director. Return JSON."},
            {"role": "user", "content": prompt}
        ],
        "model": model,
        "stream": False,
        "temperature": 0.7,
        "response_format": {"type": "json_object"}
    }
    try:
        resp = requests.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return json.loads(resp.json()['choices'][0]['message']['content'])
    except Exception as e:
        st.error(f"Text Gen Error: {e} - {resp.text if 'resp' in locals() else ''}")
        return None

def xai_generate_image(api_key, prompt):
    """Генерація картинки (Grok-2)"""
    url = "https://api.x.ai/v1/images/generations"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "prompt": prompt,
        "model": "grok-2-image-1212", # Найновіша модель для фото
        "size": "1024x1024",
        "n": 1,
        "response_format": "url"
    }
    try:
        resp = requests.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()['data'][0]['url']
    except Exception as e:
        st.error(f"Img Gen Error: {e}")
        return None

def xai_generate_voice(api_key, text, output_file):
    """Генерація голосу (Новий Grok Voice API)"""
    # Ендпоінт зі слів Грока (може відрізнятися, це тест!)
    url = "https://api.x.ai/v1/voice/generations" 
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "input": text,
        "model": "grok-voice-1", # Припускаємо назву моделі
        "voice": "en-US-1", # Припускаємо ID голосу
        "response_format": "mp3"
    }
    try:
        resp = requests.post(url, headers=headers, json=payload)
        if resp.status_code == 404:
            st.warning("⚠️ Voice API ще не доступний за цією адресою. Спробуй пізніше.")
            return None
        resp.raise_for_status()
        
        with open(output_file, "wb") as f:
            f.write(resp.content)
        return output_file
    except Exception as e:
        st.error(f"Voice Gen Error: {e} (Перевір доступ до бети)")
        return None

# --- ДОДАТКОВІ ФУНКЦІЇ ---
def save_file_from_url(url, filename):
    r = requests.get(url)
    with open(filename, 'wb') as f: f.write(r.content)
    return filename

def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except FileNotFoundError: return False

def create_zoom_video(image_path, output_path, duration):
    """Економна анімація картинки (якщо відео API не спрацює)"""
    img_abs = os.path.abspath(image_path)
    out_abs = os.path.abspath(output_path)
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", img_abs,
        "-vf", f"zoompan=z='min(zoom+0.0015,1.5)':d={int(duration*25)}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)',scale=1280:720,setsar=1",
        "-c:v", "libx264", "-t", str(duration), "-pix_fmt", "yuv420p", "-r", "25", out_abs
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return out_abs

def assemble_video(clips, voice_path, output_path):
    list_file = os.path.abspath("clips.txt")
    with open(list_file, "w") as f:
        for clip in clips: f.write(f"file '{clip}'\n")
    
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file]
    
    if voice_path and os.path.exists(voice_path):
        cmd += ["-i", os.path.abspath(voice_path), "-c:v", "libx264", "-c:a", "aac", "-shortest"]
    else:
        cmd += ["-c:v", "libx264", "-an"] # Без звуку
        
    cmd.append(output_path)
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_path

# ==========================================
# 2. ІНТЕРФЕЙС
# ==========================================
with st.sidebar:
    st.title("🌌 xAI (Grok) Studio")
    xai_key = st.text_input("xAI API Key", type="password", value="[ВСТАВ КЛЮЧ XAI]")
    
    st.info("Цей інструмент використовує **тільки xAI** для тексту, картинок та (експериментально) голосу.")
    
    num_scenes = st.slider("Кількість сцен:", 2, 10, 3)
    topic = st.text_input("Тема:", "Future of AI in 2026")

# ==========================================
# 3. MAIN
# ==========================================
st.title("🌌 Генератор на базі Grok")

if not check_ffmpeg(): st.error("Немає FFmpeg!"); st.stop()
if "[" in xai_key: st.warning("Встав ключ xAI!"); st.stop()

if st.button("🚀 ЗАПУСТИТИ GROK-CYCLE"):
    
    with st.status("🤖 Grok працює...", expanded=True) as status:
        
        # 1. SCENARIO
        st.write("🧠 1. Пишу сценарій (grok-beta)...")
        prompt = f"""
        Topic: '{topic}'. Create {num_scenes} scenes.
        Output JSON: {{
            "narration": "Script text for voiceover",
            "scenes": ["Visual prompt 1", "Visual prompt 2"...]
        }}
        """
        # Пробуємо використати нову модель, якщо ні - відкат на beta
        try:
            data = xai_chat_completion(xai_key, prompt, model="grok-beta") # Або grok-4 якщо доступний
        except:
            st.error("Помилка генерації тексту.")
            st.stop()
            
        if not data: st.stop()
        st.caption(data['narration'][:100] + "...")

        # 2. VOICE (New Feature?)
        st.write("🎙️ 2. Пробую xAI Voice API...")
        voice_path = "grok_voice.mp3"
        # Спроба викликати новий ендпоінт
        res_voice = xai_generate_voice(xai_key, data['narration'], voice_path)
        
        if res_voice:
            st.success("✅ Голос згенеровано через Grok!")
            st.audio(voice_path)
            voice_dur = get_audio_duration(voice_path)
        else:
            st.warning("⚠️ Grok Voice API недоступний (404). Відео буде німим (або додай свій файл).")
            voice_path = None
            voice_dur = num_scenes * 5 # Дефолтний час

        # 3. VISUALS
        st.write("🎨 3. Генерую зображення (Grok-2)...")
        clips = []
        time_per_scene = voice_dur / len(data['scenes'])
        
        prog = st.progress(0)
        for i, scene_p in enumerate(data['scenes']):
            # Генеруємо картинку
            img_url = xai_generate_image(xai_key, scene_p)
            if img_url:
                local_img = save_file_from_url(img_url, f"scene_{i}.jpg")
                st.image(local_img, width=200)
                
                # Поки що робимо Zoom (відео від Грока ще в закритій беті зазвичай)
                clip = create_zoom_video(local_img, f"clip_{i}.mp4", time_per_scene)
                clips.append(clip)
            
            prog.progress((i+1)/len(data['scenes']))

        # 4. ASSEMBLY
        st.write("🎬 4. Монтаж...")
        res = assemble_video(clips, voice_path, "GROK_FULL.mp4")
        
        status.update(label="✅ ГОТОВО!", state="complete")

    if res:
        st.balloons()
        st.success("Відео готове!")
        st.video(res)