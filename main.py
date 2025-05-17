import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # DON'T CHANGE THIS !!!

from flask import Flask, render_template, request, jsonify, redirect, url_for
import google.generativeai as genai
import json
import base64
from PIL import Image
import io
import os
from datetime import datetime

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size
app.config['UPLOAD_FOLDER'] = os.path.join(app.static_folder, 'uploads')

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/analyze', methods=['POST'])
def analyze_image():
    # Check if API key is provided
    api_key = request.form.get('api_key')
    if not api_key:
        return jsonify({'error': 'API key is required'}), 400
    
    # Configure Gemini API
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        return jsonify({'error': f'Invalid API key: {str(e)}'}), 400
    
    # Check if image is provided
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No image selected'}), 400
    
    try:
        # Save the uploaded image
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{timestamp}_{file.filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Open the image with PIL
        image = Image.open(filepath)
        
        # Analyze the image with Gemini
        result = analyze_waste_image(image)
        
        # Get material type and classification
        material = result.get("material", "")
        classification = result.get("classificacao", "")
        
        # Calculate environmental impact
        weight = float(request.form.get('weight', 0.1))
        impact_data = calculate_environmental_impact(material, weight)
        
        # Get collection points
        collection_points = get_collection_points(classification)
        
        # Return the results
        return jsonify({
            'analysis': result,
            'impact': impact_data,
            'collection_points': collection_points,
            'image_path': f'/static/uploads/{filename}'
        })
        
    except Exception as e:
        return jsonify({'error': f'Error processing image: {str(e)}'}), 500

def analyze_waste_image(image):
    """
    Analyzes an image of waste using the Gemini-Pro-Vision model.
    
    Args:
        image: PIL Image to be analyzed
    
    Returns:
        dict: Analysis result containing material type, instructions, and alternatives
    """
    try:
        # Configure the Gemini-Pro-Vision model
        model = genai.GenerativeModel('gemini-pro-vision')
        
        # Detailed prompt to guide the model's analysis
        prompt = """
        Analyze this image of waste and provide the following information:
        
        1. IDENTIFICAÇÃO: What type of material/waste is this? Be specific.
        2. CLASSIFICAÇÃO: Is this item recyclable, compostable, regular trash, or special waste?
        3. INSTRUÇÕES DE DESCARTE: How should this item be properly disposed of? Include preparation steps (cleaning, disassembly, etc.) if necessary.
        4. IMPACTO AMBIENTAL: What is the environmental impact of this type of waste when improperly disposed of?
        5. ALTERNATIVAS SUSTENTÁVEIS: Are there more sustainable alternatives to this item? Suggest at least 2 options.
        
        Format your response in JSON with the following keys: 
        "material", "classificacao", "instrucoes_descarte", "impacto_ambiental", "alternativas_sustentaveis"
        """
        
        # Generate the model response
        response = model.generate_content([prompt, image])
        
        # Extract the text from the response
        response_text = response.text
        
        # Try to extract the JSON from the response
        try:
            # Find the start and end of the JSON in the response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)
                return result
            else:
                # If JSON is not found, try to structure the response manually
                result = {
                    "material": "Not identified",
                    "classificacao": "Not identified",
                    "instrucoes_descarte": "Not available",
                    "impacto_ambiental": "Not available",
                    "alternativas_sustentaveis": []
                }
                
                # Extract information from the response text
                if "IDENTIFICAÇÃO" in response_text:
                    material_section = response_text.split("IDENTIFICAÇÃO:")[1].split("\n")[0].strip()
                    result["material"] = material_section
                
                if "CLASSIFICAÇÃO" in response_text:
                    class_section = response_text.split("CLASSIFICAÇÃO:")[1].split("\n")[0].strip()
                    result["classificacao"] = class_section
                
                if "INSTRUÇÕES DE DESCARTE" in response_text:
                    instr_section = response_text.split("INSTRUÇÕES DE DESCARTE:")[1].split("IMPACTO AMBIENTAL")[0].strip()
                    result["instrucoes_descarte"] = instr_section
                
                if "IMPACTO AMBIENTAL" in response_text:
                    impact_section = response_text.split("IMPACTO AMBIENTAL:")[1].split("ALTERNATIVAS SUSTENTÁVEIS")[0].strip()
                    result["impacto_ambiental"] = impact_section
                
                if "ALTERNATIVAS SUSTENTÁVEIS" in response_text:
                    alt_section = response_text.split("ALTERNATIVAS SUSTENTÁVEIS:")[1].strip()
                    result["alternativas_sustentaveis"] = [alt.strip() for alt in alt_section.split("-") if alt.strip()]
                
                return result
        
        except Exception as e:
            return {"resposta_completa": response_text}
    
    except Exception as e:
        return {"error": str(e)}

def calculate_environmental_impact(material, weight=0.1):
    """
    Calculates the positive environmental impact of proper disposal.
    
    Args:
        material (str): Type of material
        weight (float): Estimated weight in kg (default: 0.1kg)
    
    Returns:
        dict: Environmental impact metrics
    """
    # Knowledge base with impact factors per kg of material
    impact_factors = {
        "plástico": {
            "co2_evitado": 6.0,  # kg of CO2 avoided per kg of recycled plastic
            "agua_economizada": 100.0,  # liters of water saved
            "energia_economizada": 5.0,  # kWh of energy saved
            "espaco_aterro": 0.05  # m³ of landfill space saved
        },
        "papel": {
            "co2_evitado": 3.5,
            "agua_economizada": 50.0,
            "energia_economizada": 4.0,
            "espaco_aterro": 0.03
        },
        "vidro": {
            "co2_evitado": 0.3,
            "agua_economizada": 15.0,
            "energia_economizada": 0.3,
            "espaco_aterro": 0.02
        },
        "metal": {
            "co2_evitado": 9.0,
            "agua_economizada": 40.0,
            "energia_economizada": 14.0,
            "espaco_aterro": 0.04
        },
        "orgânico": {
            "co2_evitado": 0.5,
            "agua_economizada": 5.0,
            "energia_economizada": 0.1,
            "espaco_aterro": 0.01,
            "adubo_gerado": 0.3  # kg of compost generated per kg of organic waste
        },
        "eletrônico": {
            "co2_evitado": 20.0,
            "agua_economizada": 200.0,
            "energia_economizada": 25.0,
            "espaco_aterro": 0.02,
            "metais_recuperados": 0.1  # kg of metals recovered
        }
    }
    
    # Identify the material category
    material_lower = material.lower()
    category = "plástico"  # default category
    
    if any(term in material_lower for term in ["papel", "papelão", "jornal", "revista"]):
        category = "papel"
    elif any(term in material_lower for term in ["vidro", "garrafa"]):
        category = "vidro"
    elif any(term in material_lower for term in ["metal", "alumínio", "lata", "aço"]):
        category = "metal"
    elif any(term in material_lower for term in ["orgânico", "comida", "alimento", "resto"]):
        category = "orgânico"
    elif any(term in material_lower for term in ["eletrônico", "bateria", "pilha", "computador", "celular"]):
        category = "eletrônico"
    
    # Get the impact factors for the category
    factors = impact_factors.get(category, impact_factors["plástico"])
    
    # Calculate the impact based on weight
    impact = {}
    for key, value in factors.items():
        impact[key] = round(value * weight, 3)
    
    # Add equivalences for easier understanding
    equivalents = {}
    
    if "co2_evitado" in impact:
        # CO2 equivalence: km not driven by car (0.2 kg CO2/km)
        equivalents["km_carro_evitados"] = round(impact["co2_evitado"] / 0.2, 1)
    
    if "agua_economizada" in impact:
        # Water equivalence: 500ml bottles
        equivalents["garrafas_agua"] = round(impact["agua_economizada"] / 0.5, 1)
    
    if "energia_economizada" in impact:
        # Energy equivalence: hours of TV (0.1 kWh/hour)
        equivalents["horas_tv"] = round(impact["energia_economizada"] / 0.1, 1)
    
    return {
        "impacto": impact,
        "equivalencias": equivalents,
        "categoria": category
    }

def get_collection_points(material_type):
    """
    Returns suitable collection points for the material type.
    
    Args:
        material_type (str): Type of material/classification
    
    Returns:
        list: List of collection points
    """
    # Simulated knowledge base - in a real application, this would be an API or database
    collection_points = {
        "reciclável": [
            {"nome": "Cooperativa ReciclaVida", "tipo": "Cooperativa de reciclagem", 
             "materiais": ["papel", "plástico", "metal", "vidro"], 
             "endereco": "Av. Sustentável, 123", "lat": -23.550520, "lng": -46.633308},
            {"nome": "Ecoponto Municipal", "tipo": "Ponto de entrega voluntária", 
             "materiais": ["papel", "plástico", "metal", "vidro", "óleo de cozinha"], 
             "endereco": "Rua Ecológica, 456", "lat": -23.557920, "lng": -46.639825},
            {"nome": "Supermercado Verde", "tipo": "Ponto de entrega em supermercado", 
             "materiais": ["plástico", "papel", "metal"], 
             "endereco": "Av. das Árvores, 789", "lat": -23.543430, "lng": -46.642230}
        ],
        "compostável": [
            {"nome": "Horta Comunitária Central", "tipo": "Composteira comunitária", 
             "materiais": ["restos de alimentos", "folhas", "borra de café"], 
             "endereco": "Praça das Flores, s/n", "lat": -23.553240, "lng": -46.636550},
            {"nome": "Projeto Composta SP", "tipo": "Composteira municipal", 
             "materiais": ["resíduos orgânicos", "podas de jardim"], 
             "endereco": "Rua das Sementes, 321", "lat": -23.561320, "lng": -46.631240}
        ],
        "especial": [
            {"nome": "Centro de Reciclagem Tecnológica", "tipo": "Descarte de eletrônicos", 
             "materiais": ["eletrônicos", "pilhas", "baterias", "lâmpadas"], 
             "endereco": "Av. da Tecnologia, 987", "lat": -23.548720, "lng": -46.638120},
            {"nome": "Farmácia EcoSaúde", "tipo": "Descarte de medicamentos", 
             "materiais": ["medicamentos vencidos"], 
             "endereco": "Rua da Saúde, 654", "lat": -23.559840, "lng": -46.634670}
        ]
    }
    
    # Determine the appropriate category based on material type
    category = "reciclável"  # default category
    
    material_lower = material_type.lower()
    if any(term in material_lower for term in ["orgânico", "compostável", "compost", "alimento"]):
        category = "compostável"
    elif any(term in material_lower for term in ["especial", "eletrônico", "tóxico", "perigoso", "pilha", "bateria", "lâmpada", "medicamento"]):
        category = "especial"
    
    # Return the collection points for the identified category
    return collection_points.get(category, collection_points["reciclável"])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
