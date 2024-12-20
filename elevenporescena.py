import streamlit as st
import requests
import io
from datetime import datetime
import json
import time
import os
import zipfile
import pandas as pd

# Inicialización del estado de la sesión
if 'current_generation' not in st.session_state:
    st.session_state.current_generation = {
        'zip_contents': None,
        'timestamp': None,
        'files_generated': False
    }

def split_text_for_tts(text, max_chars=250):
    """
    Divide el texto en fragmentos más pequeños respetando puntuación
    """
    paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
    fragments = []
    current_fragment = ""
    
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            fragments.append(paragraph)
            continue
            
        sentences = [s.strip() + '.' for s in paragraph.replace('. ', '.').split('.') if s.strip()]
        
        for sentence in sentences:
            if len(sentence) > max_chars:
                parts = sentence.split(',')
                current_part = ""
                
                for part in parts:
                    part = part.strip()
                    if len(current_part) + len(part) + 2 <= max_chars:
                        current_part = (current_part + ", " + part).strip(", ")
                    else:
                        if current_part:
                            fragments.append(current_part + ".")
                        current_part = part
                
                if current_part:
                    fragments.append(current_part + ".")
                    
            elif len(current_fragment + sentence) > max_chars:
                if current_fragment:
                    fragments.append(current_fragment.strip())
                current_fragment = sentence
            else:
                current_fragment = (current_fragment + " " + sentence).strip()
        
        if current_fragment:
            fragments.append(current_fragment)
            current_fragment = ""
    
    if current_fragment:
        fragments.append(current_fragment)
    
    return fragments

def generate_audio_with_retries(text, api_key, voice_id, stability, similarity, use_speaker_boost, 
                              scene_number, fragment_number, retries=2, model_id="eleven_multilingual_v2"):
    """
    Genera audio usando la API de Eleven Labs con reintentos automáticos
    """
    results = []
    letters = ['a', 'b', 'c']
    
    for attempt in range(retries + 1):
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": api_key
        }
        
        data = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity,
                "style": 0,
                "use_speaker_boost": use_speaker_boost
            }
        }
        
        try:
            response = requests.post(url, json=data, headers=headers)
            if response.status_code == 200:
                # Modificado para incluir número de escena
                filename = f"escena{scene_number}_parte{fragment_number}{letters[attempt]}.mp3"
                results.append({
                    'content': response.content,
                    'filename': filename,
                    'text': text,
                    'scene': scene_number
                })
                time.sleep(5.5)
            else:
                st.warning(f"Error en intento {attempt + 1}: {response.status_code}")
        except Exception as e:
            st.error(f"Error en la solicitud: {str(e)}")
    
    return results

def get_available_voices(api_key):
    """
    Obtiene la lista de voces disponibles de Eleven Labs
    """
    url = "https://api.elevenlabs.io/v1/voices"
    headers = {
        "Accept": "application/json",
        "xi-api-key": api_key
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            voices = response.json()["voices"]
            return {voice["name"]: voice["voice_id"] for voice in voices}
        return {}
    except:
        return {}

def create_zip_files_by_version(audio_files):
    """
    Crea archivos ZIP separados para cada versión (a, b, c)
    """
    files_by_version = {
        'a': [],
        'b': [],
        'c': []
    }
    
    for audio in audio_files:
        version = audio['filename'][-5]  # Obtiene la letra de la versión
        files_by_version[version].append(audio)
    
    zip_contents = {}
    for version, files in files_by_version.items():
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Organizar por escenas
            files_by_scene = {}
            for audio in files:
                scene_num = audio['scene']
                if scene_num not in files_by_scene:
                    files_by_scene[scene_num] = []
                files_by_scene[scene_num].append(audio)
            
            # Crear estructura de carpetas por escena
            for scene_num, scene_files in files_by_scene.items():
                scene_folder = f"escena_{scene_num}"
                for audio in scene_files:
                    file_path = f"{scene_folder}/{audio['filename']}"
                    zip_file.writestr(file_path, audio['content'])
        
        zip_contents[version] = zip_buffer.getvalue()
    
    return zip_contents

def main():
    st.title("🎙️ Generador de Audio con Eleven Labs - Versión Excel")
    st.write("Genera audio por escenas desde un archivo Excel")
    
    # Configuración en la barra lateral
    st.sidebar.header("Configuración")
    
    st.sidebar.markdown("""
    ### 📑 Formato del Excel
    - Columna A: Texto de la escena
    - Cada fila es una escena diferente
    
    ### 🔄 Sistema de reintentos
    - Cada escena se generará 3 veces
    - Los archivos se nombrarán: escena1_parte1a, escena1_parte1b, etc.
    """)
    
    api_key = st.sidebar.text_input("API Key de Eleven Labs", type="password")
    
    max_chars = st.sidebar.number_input("Máximo de caracteres por fragmento", 
                                      min_value=100, 
                                      max_value=500, 
                                      value=250)
    
    stability = st.sidebar.slider("Stability", 
                                min_value=0.0, 
                                max_value=1.0, 
                                value=0.5,
                                step=0.01)
    
    similarity = st.sidebar.slider("Similarity", 
                                 min_value=0.0, 
                                 max_value=1.0, 
                                 value=0.75,
                                 step=0.01)
                                 
    use_speaker_boost = st.sidebar.checkbox("Speaker Boost", value=True)
    
    if api_key:
        voices = get_available_voices(api_key)
        if voices:
            selected_voice_name = st.sidebar.selectbox("Seleccionar voz", 
                                                     list(voices.keys()))
            voice_id = voices[selected_voice_name]
        else:
            st.sidebar.error("No se pudieron cargar las voces. Verifica tu API key.")
            return
    
    # Subida de archivo Excel
    uploaded_file = st.file_uploader("Sube tu archivo Excel", type=['xlsx', 'xls'])
    
    if uploaded_file is not None:
        try:
            # Leer el archivo Excel de manera segura
            bytes_data = uploaded_file.getvalue()
            excel_buffer = io.BytesIO(bytes_data)
            
            # Usar openpyxl explícitamente como el engine
            df = pd.read_excel(excel_buffer, engine='openpyxl')
            
            # Verificar que hay datos
            if df.empty:
                st.error("El archivo Excel está vacío")
                return
                
            st.success("Archivo Excel cargado correctamente")
            
            # Mostrar preview de las escenas
            st.subheader("Vista previa de escenas")
            st.dataframe(df)
            
            if st.button("Procesar escenas y generar audios"):
                if not api_key:
                    st.warning("Por favor ingresa la API key.")
                    return
                
                all_audio_files = []
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                total_scenes = len(df)
                current_progress = 0
                
                for index, row in df.iterrows():
                    scene_number = index + 1
                    scene_text = str(row.iloc[0])  # Asume que el texto está en la primera columna
                    
                    status_text.text(f"Procesando escena {scene_number}/{total_scenes}...")
                    
                    # Dividir el texto de la escena en fragmentos si es necesario
                    fragments = split_text_for_tts(scene_text, max_chars)
                    
                    for i, fragment in enumerate(fragments, 1):
                        audio_results = generate_audio_with_retries(
                            fragment,
                            api_key,
                            voice_id,
                            stability,
                            similarity,
                            use_speaker_boost,
                            scene_number,
                            i
                        )
                        
                        all_audio_files.extend(audio_results)
                        
                        with st.expander(f"Escena {scene_number} - Parte {i}"):
                            st.write(fragment)
                            for result in audio_results:
                                st.audio(result['content'], format="audio/mp3")
                                st.caption(f"Versión: {result['filename']}")
                    
                    current_progress += 1
                    progress_bar.progress(current_progress / total_scenes)
                
                status_text.text("¡Proceso completado! Preparando archivos ZIP...")
                
                if all_audio_files:
                    st.session_state.current_generation = {
                        'zip_contents': create_zip_files_by_version(all_audio_files),
                        'timestamp': datetime.now().strftime("%Y%m%d_%H%M%S"),
                        'files_generated': True
                    }
        
        except Exception as e:
            st.error(f"Error al procesar el archivo Excel: {str(e)}")
    
    # Mostrar los botones de descarga si hay archivos generados
    if st.session_state.current_generation['files_generated']:
        st.subheader("📥 Descargar archivos generados")
        
        col1, col2, col3 = st.columns(3)
        
        zip_contents = st.session_state.current_generation['zip_contents']
        timestamp = st.session_state.current_generation['timestamp']
        
        with col1:
            st.download_button(
                label="⬇️ Descargar versión A",
                data=zip_contents['a'],
                file_name=f"escenas_versionA_{timestamp}.zip",
                mime="application/zip",
                key="download_a"
            )
        
        with col2:
            st.download_button(
                label="⬇️ Descargar versión B",
                data=zip_contents['b'],
                file_name=f"escenas_versionB_{timestamp}.zip",
                mime="application/zip",
                key="download_b"
            )
        
        with col3:
            st.download_button(
                label="⬇️ Descargar versión C",
                data=zip_contents['c'],
                file_name=f"escenas_versionC_{timestamp}.zip",
                mime="application/zip",
                key="download_c"
            )
        
        st.success("Los archivos están listos para descargar. Cada versión (A, B, C) contiene todas las escenas organizadas en carpetas.")

if __name__ == "__main__":
    main()
