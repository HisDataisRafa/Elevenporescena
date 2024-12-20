import streamlit as st
import requests
import io
from datetime import datetime
import json
import time
import os
import zipfile

# Inicialización del estado de la sesión
if 'current_generation' not in st.session_state:
    st.session_state.current_generation = {
        'zip_contents': None,
        'timestamp': None,
        'files_generated': False
    }

def split_into_scenes(text):
    """
    Divide el texto en escenas usando '//' como separador
    y limpia cada escena
    """
    # Dividir por '//' y limpiar espacios en blanco
    scenes = [scene.strip() for scene in text.split('//') if scene.strip()]
    return scenes

def generate_audio_with_retries(text, api_key, voice_id, stability, similarity, use_speaker_boost, 
                              scene_number, retries=2, model_id="eleven_multilingual_v2"):
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
                filename = f"escena_{scene_number}{letters[attempt]}.mp3"
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
            for audio in files:
                zip_file.writestr(audio['filename'], audio['content'])
        
        zip_contents[version] = zip_buffer.getvalue()
    
    return zip_contents

def main():
    st.title("🎙️ Generador de Audio con Eleven Labs - Por Escenas")
    st.write("Genera audio de cada escena con tres versiones diferentes")
    
    # Configuración en la barra lateral
    st.sidebar.header("Configuración")
    
    st.sidebar.markdown("""
    ### 🎬 Formato del texto
    - Ingresa el texto completo
    - Separa cada escena con //
    - Ejemplo: "Escena 1 texto... // Escena 2 texto... // Escena 3 texto..."
    - Cada escena se generará 3 veces
    
    ### 🔄 Sistema de reintentos
    - Versiones: A, B y C por cada escena
    - Los archivos se nombrarán: escena_1a.mp3, escena_1b.mp3, etc.
    """)
    
    api_key = st.sidebar.text_input("API Key de Eleven Labs", type="password")
    
    model_id = "eleven_multilingual_v2"
    st.sidebar.markdown("""
    **Modelo:** Eleven Multilingual v2
    - Soporta 29 idiomas
    - Ideal para voiceovers y audiolibros
    """)
    
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
    
    text_input = st.text_area("Ingresa el texto completo", height=300)
    
    if st.button("Procesar escenas y generar audios"):
        if not text_input or not api_key:
            st.warning("Por favor ingresa el texto y la API key.")
            return
        
        # Dividir en escenas
        scenes = split_into_scenes(text_input)
        st.info(f"Se han detectado {len(scenes)} escenas. Se generarán 3 versiones de cada una.")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        all_audio_files = []
        total_scenes = len(scenes)
        
        for i, scene in enumerate(scenes, 1):
            status_text.text(f"Procesando escena {i}/{total_scenes}...")
            
            # Mostrar preview de la escena actual
            with st.expander(f"Escena {i}"):
                st.write(scene)
                
                audio_results = generate_audio_with_retries(
                    scene,
                    api_key,
                    voice_id,
                    stability,
                    similarity,
                    use_speaker_boost,
                    i
                )
                
                all_audio_files.extend(audio_results)
                
                # Mostrar los audios generados
                for result in audio_results:
                    st.audio(result['content'], format="audio/mp3")
                    st.caption(f"Versión: {result['filename']}")
            
            progress_bar.progress((i) / total_scenes)
        
        status_text.text("¡Proceso completado! Preparando archivos ZIP...")
        
        if all_audio_files:
            st.session_state.current_generation = {
                'zip_contents': create_zip_files_by_version(all_audio_files),
                'timestamp': datetime.now().strftime("%Y%m%d_%H%M%S"),
                'files_generated': True
            }
    
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
        
        st.success("Los archivos están listos para descargar. Cada versión (A, B, C) contiene todas las escenas.")

if __name__ == "__main__":
    main()
