import gradio as gr
import json
import os
import time
from PIL import Image
import io
import sys
import shutil

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils.image_generation import generate_image
from config import MODELS, DEFAULT_IMAGE_SIZE

def load_personas(file_path):
    personas = []
    try:
        # Handle both absolute and relative paths
        if isinstance(file_path, str):
            if not file_path.startswith('/'):
                file_path = os.path.join(os.getcwd(), file_path)
        else:
            # If file_path is not a string (e.g., it's a temporary file object from Gradio)
            # Copy file to uploads directory with unique name
            upload_dir = os.path.join(os.path.dirname(__file__), 'uploads')
            timestamp = int(time.time())
            safe_filename = f"{timestamp}_{os.path.basename(file_path.name)}"
            dest_path = os.path.join(upload_dir, safe_filename)
            
            # Copy file with proper error handling
            try:
                with open(file_path.name, 'rb') as src:
                    content = src.read()
                with open(dest_path, 'wb') as dst:
                    dst.write(content)
                os.chmod(dest_path, 0o666)  # Read/write for all users
            except IOError as e:
                print(f"DEBUG: Error copying file: {e}")
                return f"Error copying file: {str(e)}"
                
            file_path = dest_path
            
        print(f"DEBUG: Attempting to load file from: {file_path}")
        print(f"DEBUG: Current working directory: {os.getcwd()}")
        print(f"DEBUG: File path type: {type(file_path)}")
        
        if not os.path.exists(file_path):
            error_msg = f"File not found: {file_path}"
            print(f"DEBUG: {error_msg}")
            return error_msg
            
        with open(file_path, 'r') as f:
            content = f.read()
            print(f"DEBUG: File content length: {len(content)}")
            for line in content.splitlines():
                if line.strip():  # Skip empty lines
                    try:
                        persona = json.loads(line.strip())
                        display_str = f"{persona['name']} - {persona['occupation']}"
                        personas.append({"display": display_str, "data": persona})
                        print(f"DEBUG: Added persona: {display_str}")
                    except json.JSONDecodeError as je:
                        print(f"DEBUG: Error parsing line: {line.strip()}")
                        continue
                    except KeyError as ke:
                        print(f"DEBUG: Missing required field: {ke}")
                        continue
                    
        if not personas:
            error_msg = "No valid personas found in file"
            print(f"DEBUG: {error_msg}")
            return error_msg
            
        print(f"DEBUG: Successfully loaded {len(personas)} personas")
        return personas
        
    except Exception as e:
        error_msg = f"Error loading file: {str(e)}"
        print(f"DEBUG: {error_msg}")
        return error_msg

def generate_image_from_persona(persona_display, personas_data, model="gpt4"):
    print(f"DEBUG: Generating image for persona: {persona_display} using model: {model}")
    if not persona_display or not personas_data:
        print("DEBUG: Missing persona display or data")
        return None
        
    # Find the selected persona data
    selected_persona = None
    for persona in personas_data:
        if persona["display"] == persona_display:
            selected_persona = persona["data"]
            print(f"DEBUG: Found matching persona: {selected_persona}")
            break
            
    if not selected_persona:
        # Try matching just the name part
        name_part = persona_display.split(" - ")[0] if " - " in persona_display else persona_display
        for persona in personas_data:
            if persona["data"]["name"] == name_part:
                selected_persona = persona["data"]
                print(f"DEBUG: Found persona by name: {selected_persona}")
                break
                
    if not selected_persona:
        print("DEBUG: No matching persona found")
        return None

    # Generate prompt from persona data
    prompt = f"A portrait of {selected_persona['name']}, a {selected_persona['age']} year old {selected_persona['occupation']}. {selected_persona['personality']}"
    
    try:
        # Generate image using selected model with caching
        print(f"DEBUG: Generating image with model {model} and prompt: {prompt}")
        image = generate_image(model, prompt, DEFAULT_IMAGE_SIZE)
        if image is None:
            print("DEBUG: Image generation returned None")
            return None
            
        print("DEBUG: Image generation successful")
        return image
    except Exception as e:
        print(f"ERROR: Image generation failed - {str(e)}")
        return None

def create_interface():
    # Store personas data in the interface scope
    class Store:
        def __init__(self):
            self.personas_data = []
            self.current_file = None
            self.current_persona = None
    store = Store()
    
    # Set up local directories for uploads and cache
    base_dir = os.path.dirname(__file__)
    cache_dir = os.path.join(base_dir, 'gradio_cache')
    upload_dir = os.path.join(base_dir, 'uploads')
    
    # Ensure directories exist with proper permissions
    for directory in [cache_dir, upload_dir]:
        os.makedirs(directory, exist_ok=True)
        os.chmod(directory, 0o777)  # Full permissions for user/group/others
    
    # Configure Gradio to use local directories
    os.environ['GRADIO_TEMP_DIR'] = cache_dir
    os.environ['GRADIO_CACHE_DIR'] = cache_dir
    
    with gr.Blocks(theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            """
            # 👤 Persona Visualizer
            Upload a JSONL file containing persona information, select a persona, and generate a visual representation.
            """
        )
        
        with gr.Row():
            with gr.Column(scale=1):
                file_input = gr.File(
                    label="Upload Persona JSONL File",
                    file_types=[".jsonl"],
                    file_count="single",
                    type="filepath",
                    interactive=True,
                    visible=True,
                    value="sample_personas.jsonl"
                )
                load_button = gr.Button("Load Personas", variant="primary", interactive=True)
                status_text = gr.Textbox(
                    label="Status",
                    interactive=False,
                    visible=True,
                    value="Please upload a JSONL file"
                )
                persona_dropdown = gr.Dropdown(
                    label="Select Persona",
                    choices=[],
                    interactive=False,
                    container=True,
                    value=None,
                    allow_custom_value=False,
                    scale=1,
                    elem_id="persona_select",
                    render=True
                )
                model_choice = gr.Radio(
                    choices=list(MODELS.keys()),
                    value=list(MODELS.keys())[0],
                    label="Select Model",
                    interactive=True
                )
                generate_btn = gr.Button(
                    "🎨 Generate Visualization",
                    variant="primary",
                    interactive=False
                )
            
            with gr.Column(scale=2):
                image_output = gr.Image(
                    label="Generated Visualization",
                    container=True
                )
                status_output = gr.Textbox(
                    label="Generation Status",
                    interactive=False,
                    visible=True
                )
        
        def update_personas(file_path):
            print(f"DEBUG: Updating personas with file path: {file_path}")
            if not file_path:
                print("DEBUG: No file path provided")
                return [
                    gr.update(choices=[], value=None, interactive=False),
                    gr.update(value="Please upload a JSONL file", visible=True),
                    gr.update(interactive=False)
                ]
            
            try:
                print(f"DEBUG: Loading personas from file: {file_path}")
                personas = load_personas(file_path)
                print(f"DEBUG: Loaded personas result: {personas}")
                
                if isinstance(personas, str):  # Error message
                    print(f"DEBUG: Error loading personas: {personas}")
                    return [
                        gr.update(choices=[], value=None, interactive=False),
                        gr.update(value=f"Error: {personas}", visible=True),
                        gr.update(interactive=False)
                    ]
                
                store.personas_data = personas
                store.current_file = file_path
                
                choices = [p["display"] for p in personas]
                store.current_persona = personas[0]["data"]
                
                print(f"DEBUG: Setting choices: {choices}")
                print(f"DEBUG: Setting current persona: {store.current_persona}")
                
                return [
                    gr.update(choices=choices, value=choices[0], interactive=True),
                    gr.update(value="✅ File loaded successfully", visible=True),
                    gr.update(interactive=True)
                ]
            except Exception as e:
                print(f"Error in update_personas: {str(e)}")
                return [
                    gr.update(choices=[], value=None, interactive=False),
                    gr.update(value=f"Error: {str(e)}", visible=True),
                    gr.update(interactive=False)
                ]
        
        def on_generate_click(persona_display, model_choice):
            print(f"DEBUG: Generate clicked for {persona_display} using {model_choice}")
            if not persona_display:
                return [
                    None, 
                    gr.update(value="Please select a persona", visible=True),
                    gr.update(value="Error: No persona selected", visible=True)
                ]
            
            try:
                model = MODELS[model_choice]
                image = generate_image_from_persona(persona_display, store.personas_data, model)
                if image is None:
                    return [
                        None, 
                        gr.update(value="Error: Could not generate visualization", visible=True),
                        gr.update(value="Failed to generate image", visible=True)
                    ]
                    
                return [
                    image,
                    gr.update(value="✅ Visualization generated successfully", visible=True),
                    gr.update(value=f"Image generated successfully using {model_choice}", visible=True)
                ]
            except Exception as e:
                error_msg = f"Error generating visualization: {str(e)}"
                print(f"DEBUG: {error_msg}")
                return [
                    None,
                    gr.update(value=error_msg, visible=True),
                    gr.update(value=f"Generation failed: {str(e)}", visible=True)
                ]
        
        # Handle file upload and persona selection
        def on_file_upload(file_obj):
            if not file_obj:
                return [
                    gr.update(choices=[], value=None, interactive=False),
                    gr.update(value="Please upload a JSONL file", visible=True),
                    gr.update(interactive=False)
                ]
            try:
                print(f"File uploaded: {file_obj}")
                result = update_personas(file_obj)
                print(f"Update result: {result}")
                return result
            except Exception as e:
                print(f"Error in file upload: {str(e)}")
                return [
                    gr.update(choices=[], value=None, interactive=False),
                    gr.update(value=f"Error: {str(e)}", visible=True),
                    gr.update(interactive=False)
                ]
            
        # Handle file loading
        load_button.click(
            fn=update_personas,
            inputs=[file_input],
            outputs=[persona_dropdown, status_text, generate_btn]
        )
        
        generate_btn.click(
            fn=on_generate_click,
            inputs=[persona_dropdown, model_choice],
            outputs=[image_output, status_text, status_output]
        )
        
        # Reset interface when file is cleared
        file_input.clear(
            lambda: [
                gr.update(choices=[], value=None, interactive=False),
                gr.update(value="Please upload a JSONL file", visible=True),
                gr.update(interactive=False)
            ],
            outputs=[persona_dropdown, status_text, generate_btn]
        )

    return demo

if __name__ == "__main__":
    demo = create_interface()
    demo.launch(server_name="0.0.0.0", share=True)
