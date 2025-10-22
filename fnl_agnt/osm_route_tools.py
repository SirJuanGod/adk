# osm_route_tools.py
import osmnx as ox
import networkx as nx
from geopy.distance import geodesic
import requests
import json
from typing import List, Dict, Optional
from datetime import datetime

# Importar herramientas
from .air_quality_tools import get_air_quality_for_all_nodes, get_quality_level
from .destination_tools_osm import find_destination_osm, find_nearest_destination

# Configurar OSM
ox.settings.log_console = False
ox.settings.use_cache = True
ox.settings.timeout = 300

def get_osm_route_with_air_quality(origin_lat: float, origin_lng: float,
                                  destination_lat: float, destination_lng: float,
                                  mode: str = "drive") -> dict:
    """
    Genera ruta REAL usando OpenStreetMap con análisis de calidad del aire.
    """
    try:
        print("🔄 Descargando mapa de Cali desde OpenStreetMap...")
        
        # 1. Obtener grafo de calles de Cali
        graph = ox.graph_from_place("Cali, Colombia", network_type=mode)
        
        # 2. Encontrar nodos más cercanos en el grafo
        origin_node = ox.distance.nearest_nodes(graph, origin_lng, origin_lat)
        destination_node = ox.distance.nearest_nodes(graph, destination_lng, destination_lat)
        
        # 3. Calcular ruta más corta
        print("🔄 Calculando ruta óptima...")
        route = nx.shortest_path(graph, origin_node, destination_node, weight='length')
        
        # 4. Obtener coordenadas detalladas de la ruta
        route_coords = []
        
        for i in range(len(route)):
            node_data = graph.nodes[route[i]]
            route_coords.append({
                'lat': node_data['y'],
                'lng': node_data['x'],
                'node_id': route[i]
            })
        
        # 5. Calcular distancia total
        route_length_m = 0
        for i in range(len(route) - 1):
            node_from = route[i]
            node_to = route[i + 1]
            edge_data = graph.get_edge_data(node_from, node_to)
            if edge_data:
                route_length_m += list(edge_data.values())[0].get('length', 0)
        
        route_length_km = route_length_m / 1000
        
        # 6. Obtener calidad del aire
        print("🔄 Analizando calidad del aire...")
        air_quality_data = get_air_quality_for_all_nodes()
        
        # 7. Generar instrucciones paso a paso
        steps = generate_detailed_route_steps(route_coords, air_quality_data, mode, route_length_km)
        
        # 8. Análisis de calidad del aire en la ruta
        route_air_quality = analyze_route_air_quality(route_coords, air_quality_data)
        
        return {
            "success": True,
            "route_type": "REAL_OSM_ROUTE",
            "route_summary": {
                "origin": {"lat": origin_lat, "lng": origin_lng, "name": "Origen"},
                "destination": {"lat": destination_lat, "lng": destination_lng, "name": "Destino"},
                "total_distance_km": round(route_length_km, 2),
                "total_distance_m": round(route_length_m, 2),
                "estimated_duration_min": round(calculate_osm_duration(route_length_km, mode), 1),
                "transport_mode": get_mode_display_name(mode),
                "nodes_in_route": len(route),
                "coordinates_count": len(route_coords)
            },
            "step_by_step_instructions": steps,
            "route_coordinates": [{"lat": coord['lat'], "lng": coord['lng']} for coord in route_coords],
            "air_quality_analysis": route_air_quality,
            "map_data": {
                "bounds": calculate_osm_bounds(route_coords),
                "center": find_route_center(route_coords),
                "origin_marker": {"lat": origin_lat, "lng": origin_lng, "type": "origin"},
                "destination_marker": {"lat": destination_lat, "lng": destination_lng, "type": "destination"}
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {"success": False, "error": f"Error en cálculo de ruta: {str(e)}"}

def generate_detailed_route_steps(route_coords: List[Dict], air_quality_data: dict, 
                                mode: str, total_distance_km: float) -> List[Dict]:
    """
    Genera instrucciones detalladas paso a paso para la ruta.
    """
    if len(route_coords) < 3:
        return generate_basic_steps(route_coords, air_quality_data, mode, total_distance_km)
    
    steps = []
    
    # Paso 1: Inicio
    steps.append({
        "step_number": 1,
        "instruction": "📍 Inicie su viaje desde el punto de origen",
        "coordinates": route_coords[0],
        "distance_from_start_km": 0.0,
        "estimated_time_min": 0.0,
        "air_quality": evaluate_point_air_quality(route_coords[0], air_quality_data),
        "icon": "📍",
        "type": "start"
    })
    
    # Dividir la ruta en segmentos significativos
    num_segments = min(8, max(3, len(route_coords) // 10))
    segment_size = len(route_coords) // num_segments
    
    for segment_idx in range(1, num_segments):
        point_idx = segment_idx * segment_size
        if point_idx >= len(route_coords):
            break
            
        current_point = route_coords[point_idx]
        distance_from_start = calculate_distance_along_route(route_coords[0], current_point)
        
        # Generar instrucción basada en el progreso
        progress = point_idx / len(route_coords)
        instruction = generate_segment_instruction(segment_idx, progress, mode)
        
        steps.append({
            "step_number": len(steps) + 1,
            "instruction": instruction,
            "coordinates": current_point,
            "distance_from_start_km": round(distance_from_start, 2),
            "estimated_time_min": round(distance_from_start / get_osm_speed_kmh(mode) * 60, 1),
            "air_quality": evaluate_point_air_quality(current_point, air_quality_data),
            "icon": get_segment_icon(segment_idx),
            "type": "navigation"
        })
    
    # Paso final: Llegada
    steps.append({
        "step_number": len(steps) + 1,
        "instruction": "🎯 Ha llegado a su destino",
        "coordinates": route_coords[-1],
        "distance_from_start_km": round(total_distance_km, 2),
        "estimated_time_min": round(total_distance_km / get_osm_speed_kmh(mode) * 60, 1),
        "air_quality": evaluate_point_air_quality(route_coords[-1], air_quality_data),
        "icon": "🎯",
        "type": "arrival"
    })
    
    return steps

def generate_segment_instruction(segment_idx: int, progress: float, mode: str) -> str:
    """Genera instrucciones contextuales basadas en el progreso."""
    mode_name = get_mode_display_name(mode)
    
    if progress < 0.3:
        return f"⬆️ Continúe por la ruta principal en {mode_name}"
    elif progress < 0.6:
        return f"➡️ Manténgase en esta vía en {mode_name}"
    elif progress < 0.9:
        return f"↗️ Se acerca a su destino en {mode_name}"
    else:
        return f"🎯 Prepare su llegada al destino final"

def get_segment_icon(segment_idx: int) -> str:
    """Obtiene ícono para el segmento."""
    icons = ["⬆️", "➡️", "↗️", "🔷", "🔶", "🚦", "🛣️", "🎯"]
    return icons[segment_idx % len(icons)]

def analyze_route_air_quality(route_coords: List[Dict], air_quality_data: dict) -> Dict:
    """Analiza la calidad del aire a lo largo de toda la ruta."""
    if not air_quality_data.get('success'):
        return {
            "average_air_quality_score": 50.0,
            "quality_level": "🔵 Sin datos",
            "message": "No hay datos disponibles de calidad del aire"
        }
    
    air_quality_nodes = air_quality_data.get('nodes_with_air_quality', [])
    
    if not air_quality_nodes:
        return {
            "average_air_quality_score": 50.0,
            "quality_level": "🔵 Sin datos",
            "message": "No se encontraron sensores de calidad del aire"
        }
    
    # Muestrear puntos a lo largo de la ruta
    sample_indices = range(0, len(route_coords), max(1, len(route_coords) // 10))
    sample_points = [route_coords[i] for i in sample_indices if i < len(route_coords)]
    
    scores = []
    quality_points = []
    
    for point in sample_points:
        nearest_node = find_nearest_air_quality_node(point['lat'], point['lng'], air_quality_nodes)
        if nearest_node:
            score = nearest_node['air_quality']['air_quality_score']
            scores.append(score)
            quality_points.append({
                "coordinates": point,
                "score": score,
                "quality_level": get_quality_level(score),
                "nearest_sensor": nearest_node['nombre']
            })
    
    if scores:
        avg_score = sum(scores) / len(scores)
        return {
            "average_air_quality_score": round(avg_score, 2),
            "quality_level": get_quality_level(avg_score),
            "samples_analyzed": len(scores),
            "min_score": round(min(scores), 2),
            "max_score": round(max(scores), 2),
            "quality_points": quality_points[:3],
            "recommendation": generate_air_quality_recommendation(avg_score)
        }
    else:
        return {
            "average_air_quality_score": 50.0,
            "quality_level": "🔵 Desconocida",
            "message": "No se pudieron obtener datos de calidad del aire en la ruta"
        }

def generate_air_quality_recommendation(score: float) -> str:
    """Genera recomendación basada en el score de calidad del aire."""
    if score >= 80:
        return "✅ Calidad del aire excelente. Ideal para actividades al aire libre."
    elif score >= 60:
        return "⚠️ Calidad del aire buena. Puede realizar su viaje normalmente."
    elif score >= 40:
        return "🔶 Calidad moderada. Personas sensibles deben considerar precauciones."
    else:
        return "🔴 Calidad del aire mala. Use mascarilla y evite actividades intensas."

def find_nearest_air_quality_node(lat: float, lng: float, air_quality_nodes: List[Dict], max_distance_km: float = 3.0) -> Optional[Dict]:
    """Encuentra el nodo de calidad del aire más cercano."""
    point = (lat, lng)
    nearest = None
    min_distance = float('inf')
    
    for node in air_quality_nodes:
        node_point = (node['lat'], node['lng'])
        distance = geodesic(point, node_point).kilometers
        
        if distance < min_distance and distance <= max_distance_km:
            min_distance = distance
            nearest = node
    
    return nearest

def evaluate_point_air_quality(point: Dict, air_quality_data: dict) -> Dict:
    """Evalúa la calidad del aire en un punto específico."""
    if not air_quality_data.get('success'):
        return {"score": 50.0, "level": "🔵 Sin datos"}
    
    air_quality_nodes = air_quality_data.get('nodes_with_air_quality', [])
    nearest = find_nearest_air_quality_node(point['lat'], point['lng'], air_quality_nodes)
    
    if nearest:
        score = nearest['air_quality']['air_quality_score']
        return {
            "score": score,
            "level": get_quality_level(score),
            "nearest_sensor": nearest['nombre'],
            "sensor_distance_km": round(geodesic((point['lat'], point['lng']), 
                                               (nearest['lat'], nearest['lng'])).kilometers, 2)
        }
    else:
        return {"score": 50.0, "level": "🔵 Sin datos cercanos"}

# Funciones de apoyo
def get_osm_speed_kmh(mode: str) -> float:
    speeds = {"drive": 40.0, "walk": 5.0, "bike": 15.0}
    return speeds.get(mode, 20.0)

def calculate_osm_duration(distance_km: float, mode: str) -> float:
    return (distance_km / get_osm_speed_kmh(mode)) * 60

def calculate_osm_bounds(route_coords: List[Dict]) -> Dict:
    lats = [p['lat'] for p in route_coords]
    lngs = [p['lng'] for p in route_coords]
    return {
        "north": max(lats),
        "south": min(lats), 
        "east": max(lngs),
        "west": min(lngs)
    }

def find_route_center(route_coords: List[Dict]) -> Dict:
    mid_idx = len(route_coords) // 2
    return {"lat": route_coords[mid_idx]['lat'], "lng": route_coords[mid_idx]['lng']}

def calculate_distance_along_route(start_point: Dict, current_point: Dict) -> float:
    return geodesic((start_point['lat'], start_point['lng']), 
                   (current_point['lat'], current_point['lng'])).kilometers

def get_mode_display_name(mode: str) -> str:
    names = {"drive": "vehículo", "walk": "caminando", "bike": "bicicleta"}
    return names.get(mode, mode)

def generate_basic_steps(route_coords: List[Dict], air_quality_data: dict, mode: str, total_distance_km: float) -> List[Dict]:
    """Genera pasos básicos cuando la ruta es muy corta."""
    steps = []
    
    steps.append({
        "step_number": 1,
        "instruction": "📍 Inicio del viaje",
        "coordinates": route_coords[0],
        "distance_from_start_km": 0.0,
        "estimated_time_min": 0.0,
        "air_quality": evaluate_point_air_quality(route_coords[0], air_quality_data),
        "icon": "📍",
        "type": "start"
    })
    
    if len(route_coords) > 2:
        mid_point = route_coords[len(route_coords)//2]
        mid_distance = calculate_distance_along_route(route_coords[0], mid_point)
        
        steps.append({
            "step_number": 2,
            "instruction": f"🎯 Continúe hacia su destino",
            "coordinates": mid_point,
            "distance_from_start_km": round(mid_distance, 2),
            "estimated_time_min": round(mid_distance / get_osm_speed_kmh(mode) * 60, 1),
            "air_quality": evaluate_point_air_quality(mid_point, air_quality_data),
            "icon": "🎯",
            "type": "navigation"
        })
    
    steps.append({
        "step_number": len(steps) + 1,
        "instruction": "✅ Ha llegado a su destino",
        "coordinates": route_coords[-1],
        "distance_from_start_km": round(total_distance_km, 2),
        "estimated_time_min": round(total_distance_km / get_osm_speed_kmh(mode) * 60, 1),
        "air_quality": evaluate_point_air_quality(route_coords[-1], air_quality_data),
        "icon": "✅",
        "type": "arrival"
    })
    
    return steps

def get_complete_route_with_osm_search(origin_lat: float, origin_lng: float,
                                     destination_query: str, 
                                     mode: str = "drive") -> dict:
    """
    Búsqueda completa: encuentra destino con OSM + genera ruta + calidad del aire.
    """
    try:
        print(f"🎯 Búsqueda completa: {destination_query}")
        
        # 1. Buscar destino usando OSM
        dest_result = find_destination_osm(destination_query)
        if not dest_result.get('success') or not dest_result['matches']:
            return {
                "success": False, 
                "error": f"No se encontró '{destination_query}' en OpenStreetMap"
            }
        
        # 2. Seleccionar el primer resultado
        destination = dest_result['matches'][0]
        print(f"📍 Destino seleccionado: {destination['nombre']}")
        
        # 3. Generar ruta con OSM
        route_result = get_osm_route_with_air_quality(
            origin_lat, origin_lng,
            destination['lat'], destination['lng'],
            mode
        )
        
        if not route_result.get('success'):
            return route_result
        
        # 4. Combinar resultados
        complete_result = {
            **route_result,
            "destination_info": destination,
            "search_query": destination_query,
            "alternative_destinations": dest_result['matches'][1:3]  # 2 alternativas
        }
        
        return complete_result
        
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_nearest_route_with_air_quality(origin_lat: float, origin_lng: float,
                                     destination_type: str, 
                                     mode: str = "drive") -> dict:
    """
    Encuentra el destino más cercano de un tipo y genera ruta.
    """
    try:
        print(f"🔍 Buscando {destination_type} más cercano...")
        
        # 1. Encontrar destino más cercano
        nearest_result = find_nearest_destination(origin_lat, origin_lng, destination_type)
        if not nearest_result.get('success'):
            return nearest_result
        
        destination = nearest_result['nearest_destination']
        print(f"📍 {destination_type} más cercano: {destination['nombre']} ({nearest_result['distance_km']}km)")
        
        # 2. Generar ruta
        route_result = get_osm_route_with_air_quality(
            origin_lat, origin_lng,
            destination['lat'], destination['lng'],
            mode
        )
        
        if not route_result.get('success'):
            return route_result
        
        # 3. Combinar resultados
        return {
            **route_result,
            "destination_info": destination,
            "nearest_search": {
                "type": destination_type,
                "straight_line_distance_km": nearest_result['distance_km'],
                "actual_route_distance_km": route_result['route_summary']['total_distance_km']
            }
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}