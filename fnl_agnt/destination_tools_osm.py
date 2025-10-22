# destination_tools_osm.py
import osmnx as ox
import requests
import json
from typing import Dict, List, Optional
from geopy.distance import geodesic

# Configurar OSM
ox.settings.log_console = False
ox.settings.use_cache = True
ox.settings.timeout = 300

def find_destination_osm(destination_name: str, location: str = "Cali, Colombia", limit: int = 5) -> dict:
    """
    Busca destinos usando OpenStreetMap (más realista y completo).
    """
    try:
        print(f"🔍 Buscando '{destination_name}' en OSM...")
        
        # 1. Primero intentar con búsqueda por tags de OSM
        matches = find_destination_by_tags(destination_name, location, limit)
        
        if matches:
            return {
                "success": True,
                "matches": matches[:limit],
                "search_term": destination_name,
                "total_matches": len(matches),
                "source": "osm_tags"
            }
        
        # 2. Si no hay resultados, usar base de datos de respaldo
        backup_matches = find_destination_backup(destination_name)
        if backup_matches:
            return {
                "success": True,
                "matches": backup_matches[:limit],
                "search_term": destination_name,
                "total_matches": len(backup_matches),
                "source": "backup_database"
            }
        
        return {
            "success": False,
            "error": f"No se encontraron resultados para '{destination_name}'",
            "search_term": destination_name
        }
        
    except Exception as e:
        print(f"Error en búsqueda OSM: {e}")
        # En caso de error, usar base de datos de respaldo
        backup_matches = find_destination_backup(destination_name)
        if backup_matches:
            return {
                "success": True,
                "matches": backup_matches[:limit],
                "search_term": destination_name,
                "total_matches": len(backup_matches),
                "source": "backup_fallback"
            }
        return {"success": False, "error": str(e)}

def find_destination_by_tags(destination_name: str, location: str = "Cali, Colombia", limit: int = 5) -> List[Dict]:
    """
    Busca destinos usando tags específicos de OSM.
    """
    try:
        destination_name_lower = destination_name.lower()
        matches = []
        
        # Mapeo de categorías a tags OSM
        tags_to_try = get_osm_tags_for_search(destination_name_lower)
        
        for tags in tags_to_try:
            try:
                print(f"Buscando con tags: {tags}")
                
                # Buscar lugares con estos tags
                places = ox.geometries_from_place(location, tags)
                
                if len(places) > 0:
                    for idx, place in places.head(limit * 2).iterrows():
                        try:
                            name = get_place_name(place, destination_name)
                            lat = float(place.geometry.centroid.y)
                            lng = float(place.geometry.centroid.x)
                            
                            # Validar coordenadas
                            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                                continue
                                
                            matches.append({
                                "nombre": name,
                                "lat": lat,
                                "lng": lng,
                                "type": get_place_type(place),
                                "address": get_place_address(place),
                                "source": "osm_tags"
                            })
                            
                            if len(matches) >= limit * 3:  # Limitar resultados
                                break
                                
                        except Exception as e:
                            print(f"Error procesando lugar: {e}")
                            continue
                            
            except Exception as e:
                print(f"Error buscando con tags {tags}: {e}")
                continue
        
        return matches
        
    except Exception as e:
        print(f"Error en búsqueda por tags: {e}")
        return []

def get_osm_tags_for_search(search_term: str) -> List[Dict]:
    """
    Genera tags OSM basados en el término de búsqueda.
    """
    search_term = search_term.lower()
    
    # Mapeo de términos de búsqueda a tags OSM
    tag_mappings = [
        # Hospitales y salud
        {"hospital": {"amenity": "hospital"}},
        {"clínica": {"amenity": "clinic"}},
        {"salud": {"amenity": ["hospital", "clinic", "doctors"]}},
        {"farmacia": {"amenity": "pharmacy"}},
        {"medico": {"amenity": "doctors"}},
        
        # Educación
        {"universidad": {"amenity": "university"}},
        {"colegio": {"amenity": "school"}},
        {"escuela": {"amenity": "school"}},
        {"educación": {"amenity": ["university", "college", "school"]}},
        
        # Comercio
        {"centro comercial": {"shop": "mall"}},
        {"supermercado": {"shop": "supermarket"}},
        {"tienda": {"shop": True}},
        {"compras": {"shop": True}},
        
        # Comida
        {"restaurante": {"amenity": "restaurant"}},
        {"café": {"amenity": "cafe"}},
        {"comida": {"amenity": ["restaurant", "cafe", "fast_food"]}},
        
        # Entretenimiento
        {"parque": {"leisure": "park"}},
        {"cine": {"amenity": "cinema"}},
        {"teatro": {"amenity": "theatre"}},
        
        # Transporte
        {"aeropuerto": {"aeroway": "aerodrome"}},
        {"estación": {"amenity": ["bus_station", "train_station"]}},
        {"bus": {"amenity": "bus_station"}},
        
        # Servicios
        {"banco": {"amenity": "bank"}},
        {"hotel": {"tourism": "hotel"}},
        {"gasolina": {"amenity": "fuel"}},
        {"policía": {"amenity": "police"}},
        {"bomberos": {"amenity": "fire_station"}}
    ]
    
    matching_tags = []
    for mapping in tag_mappings:
        for term, tags in mapping.items():
            if term in search_term:
                matching_tags.append(tags)
    
    # Si no hay coincidencias específicas, buscar como amenity general
    if not matching_tags:
        matching_tags = [{"amenity": True}, {"shop": True}, {"tourism": True}]
    
    return matching_tags

def find_destination_backup(destination_name: str) -> List[Dict]:
    """
    Base de datos de respaldo para cuando OSM no funciona.
    """
    destination_name_lower = destination_name.lower()
    
    destinations_db = {
        "hospital": [
            {"nombre": "Hospital Universitario del Valle", "lat": 3.3759, "lng": -76.5325, "type": "hospital", "address": "Calle 5 # 36-08"},
            {"nombre": "Clínica Imbanaco", "lat": 3.4205, "lng": -76.5462, "type": "hospital", "address": "Cra. 38 # 5A-100"},
            {"nombre": "Fundación Valle del Lili", "lat": 3.3686, "lng": -76.5307, "type": "hospital", "address": "Cra. 98 # 18-49"},
            {"nombre": "Hospital San Juan de Dios", "lat": 3.4512, "lng": -76.5401, "type": "hospital", "address": "Cra. 10 # 1-27"}
        ],
        "universidad": [
            {"nombre": "Universidad del Valle", "lat": 3.3759, "lng": -76.5325, "type": "university", "address": "Ciudad Universitaria Meléndez"},
            {"nombre": "Universidad Santiago de Cali", "lat": 3.4412, "lng": -76.5456, "type": "university", "address": "Calle 5 # 62-00"},
            {"nombre": "Universidad Icesi", "lat": 3.3409, "lng": -76.5301, "type": "university", "address": "Cra. 122 # 1-80"},
            {"nombre": "Universidad Autónoma de Occidente", "lat": 3.4376, "lng": -76.5465, "type": "university", "address": "Cra. 122 # 1-80"}
        ],
        "centro comercial": [
            {"nombre": "Centro Comercial Jardín Plaza", "lat": 3.3689, "lng": -76.5297, "type": "mall", "address": "Cra. 100 # 5-169"},
            {"nombre": "Centro Comercial Único", "lat": 3.4203, "lng": -76.5468, "type": "mall", "address": "Cra. 38 # 5-01"},
            {"nombre": "Centro Comercial Chipichape", "lat": 3.4926, "lng": -76.5008, "type": "mall", "address": "Cra. 38 # 53-45"}
        ],
        "parque": [
            {"nombre": "Parque del Perro", "lat": 3.4025, "lng": -76.5456, "type": "park", "address": "Calle 2 Oeste"},
            {"nombre": "Parque del Gato", "lat": 3.4518, "lng": -76.5321, "type": "park", "address": "Cra. 4 # 10-00"},
            {"nombre": "Parque de la Caña", "lat": 3.4852, "lng": -76.5051, "type": "park", "address": "Cra. 56 # 3-00"}
        ],
        "aeropuerto": [
            {"nombre": "Aeropuerto Alfonso Bonilla Aragón", "lat": 3.5432, "lng": -76.3815, "type": "airport", "address": "Palmira, Valle del Cauca"}
        ],
        "farmacia": [
            {"nombre": "Farmacia Cruz Verde", "lat": 3.4510, "lng": -76.5320, "type": "pharmacy", "address": "Cra. 4 # 10-25"},
            {"nombre": "Farmacia Dr. Simi", "lat": 3.4415, "lng": -76.5460, "type": "pharmacy", "address": "Calle 5 # 62-15"}
        ],
        "banco": [
            {"nombre": "Banco de Bogotá", "lat": 3.4515, "lng": -76.5318, "type": "bank", "address": "Cra. 4 # 10-30"},
            {"nombre": "Bancolombia", "lat": 3.4418, "lng": -76.5458, "type": "bank", "address": "Calle 5 # 62-20"}
        ]
    }
    
    matches = []
    
    # Buscar por categoría
    for category, places in destinations_db.items():
        if category in destination_name_lower:
            matches.extend(places)
    
    # Búsqueda por nombre exacto
    if not matches:
        for category, places in destinations_db.items():
            for place in places:
                if destination_name_lower in place['nombre'].lower():
                    matches.append(place)
    
    # Búsqueda parcial
    if not matches:
        for category, places in destinations_db.items():
            for place in places:
                name_words = place['nombre'].lower().split()
                search_words = destination_name_lower.split()
                if any(search_word in ' '.join(name_words) for search_word in search_words):
                    matches.append(place)
    
    return matches

def get_place_name(place, default_name: str) -> str:
    """Extrae el nombre de un lugar de OSM."""
    name_fields = ['name', 'name:es', 'name:en', 'brand', 'operator', 'amenity']
    
    for field in name_fields:
        if field in place and place[field] and str(place[field]).strip():
            name = str(place[field]).strip()
            if name and name != 'nan':
                return name
    
    # Si no hay nombre, usar el tipo de amenity
    amenity = place.get('amenity', '')
    if amenity:
        return f"{amenity.capitalize()} - {default_name}"
    
    return f"Lugar - {default_name}"

def get_place_type(place) -> str:
    """Extrae el tipo de lugar de OSM."""
    type_fields = ['amenity', 'shop', 'tourism', 'leisure', 'aeroway']
    
    for field in type_fields:
        if field in place and place[field]:
            return str(place[field])
    
    return "unknown"

def get_place_address(place) -> str:
    """Extrae la dirección de un lugar de OSM."""
    address_parts = []
    
    address_fields = ['addr:street', 'addr:housenumber', 'addr:city']
    for field in address_fields:
        if field in place and place[field] and str(place[field]).strip():
            address_parts.append(str(place[field]).strip())
    
    return ', '.join(address_parts) if address_parts else "Dirección no disponible"

def find_nearest_destination(origin_lat: float, origin_lng: float, 
                           destination_type: str, max_distance_km: float = 10.0) -> dict:
    """
    Encuentra el destino más cercano de un tipo específico.
    """
    try:
        # Buscar destinos del tipo especificado
        dest_result = find_destination_osm(destination_type)
        
        if not dest_result.get('success') or not dest_result['matches']:
            return {"success": False, "error": f"No se encontraron {destination_type}"}
        
        # Encontrar el más cercano
        origin = (origin_lat, origin_lng)
        nearest_dest = None
        min_distance = float('inf')
        
        for destination in dest_result['matches']:
            dest_point = (destination['lat'], destination['lng'])
            distance = geodesic(origin, dest_point).kilometers
            
            if distance < min_distance and distance <= max_distance_km:
                min_distance = distance
                nearest_dest = destination
        
        if nearest_dest:
            return {
                "success": True,
                "nearest_destination": nearest_dest,
                "distance_km": round(min_distance, 2),
                "origin": {"lat": origin_lat, "lng": origin_lng},
                "search_type": destination_type
            }
        else:
            return {"success": False, "error": f"No hay {destination_type} dentro de {max_distance_km}km"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

# Función de compatibilidad con el código existente
def find_destination(destination_name: str) -> dict:
    """
    Función wrapper para mantener compatibilidad con el código existente.
    """
    return find_destination_osm(destination_name)