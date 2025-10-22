# air_quality_tools.py
import requests
from geopy.distance import geodesic
from datetime import datetime
from typing import Optional, List, Dict

def get_cali_nodes() -> dict:
    """
    Obtiene todos los nodos de Cali desde la API oficial.
    """
    try:
        url = "https://apioac22.cali.gov.co/nodes"
        response = requests.get(url, headers={'accept': 'application/json'}, timeout=10)
        
        if response.status_code == 200:
            nodes = response.json()
            normalized = []
            
            for node in nodes:
                normalized.append({
                    'id': node.get('id'),
                    'nombre': node.get('name'),
                    'lat': float(node.get('latitude', 0)),
                    'lng': float(node.get('longitude', 0)),
                    'direccion': node.get('address', ''),
                    'deviceId': node.get('deviceId'),
                    'tipo': node.get('description', '')[:100] if node.get('description') else 'Punto de interés'
                })
            
            return {
                "success": True, 
                "nodes": normalized, 
                "total": len(normalized)
            }
        
        return {"success": False, "error": f"API Status: {response.status_code}"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_air_quality_metrics(deviceId: str, start_date: Optional[str] = None) -> dict:
    """
    Obtiene métricas de calidad del aire para un dispositivo específico.
    """
    try:
        if not start_date:
            start_date = datetime.now().strftime("%Y-%m-%d")
        
        url = "https://apioac22.cali.gov.co/metrics/range_public"
        params = {
            'deviceId': deviceId,
            'start_date': start_date
        }
        
        response = requests.get(
            url, 
            params=params,
            headers={'accept': 'application/json'}, 
            timeout=10
        )
        
        if response.status_code == 200:
            metrics_data = response.json()
            
            latest_data = {}
            if metrics_data and len(metrics_data) > 0:
                latest = metrics_data[-1]
                
                latest_data = {
                    "deviceId": deviceId,
                    "timestamp": latest.get('timestamp'),
                    "massPM2_5IcaAvg": latest.get('massPM2_5IcaAvg'),
                    "massPM10_0IcaAvg": latest.get('massPM10_0IcaAvg'),
                    "massPM10_0Avg": latest.get('massPM10_0Avg'),
                    "massPM2_5Avg": latest.get('massPM2_5Avg'),
                    "air_quality_score": calculate_air_quality_score(latest)
                }
            
            return {
                "success": True,
                "metrics": latest_data,
                "deviceId": deviceId,
                "date": start_date,
                "total_readings": len(metrics_data)
            }
        else:
            return {
                "success": False, 
                "error": f"API Error: {response.status_code}",
                "deviceId": deviceId
            }
            
    except Exception as e:
        return {"success": False, "error": str(e), "deviceId": deviceId}

def calculate_air_quality_score(metrics: dict) -> float:
    """
    Calcula un score de calidad del aire (0-100, donde 100 es mejor).
    """
    try:
        pm25 = metrics.get('massPM2_5Avg', 0) or 0
        pm10 = metrics.get('massPM10_0Avg', 0) or 0
        
        pm25_score = max(0, 100 - (pm25 * 2))
        pm10_score = max(0, 100 - (pm10 * 0.5))
        
        overall_score = (pm25_score * 0.7) + (pm10_score * 0.3)
        
        return round(max(0, min(100, overall_score)), 2)
    except:
        return 50.0

def get_air_quality_for_all_nodes() -> dict:
    """
    Obtiene la calidad del aire para todos los nodos que tienen deviceId.
    """
    try:
        nodes_result = get_cali_nodes()
        if not nodes_result.get('success'):
            return nodes_result
        
        nodes = nodes_result['nodes']
        air_quality_data = []
        
        for node in nodes:
            if node.get('deviceId'):
                metrics_result = get_air_quality_metrics(node['deviceId'])
                if metrics_result.get('success') and metrics_result.get('metrics'):
                    air_quality_data.append({
                        **node,
                        "air_quality": metrics_result['metrics']
                    })
        
        return {
            "success": True,
            "nodes_with_air_quality": air_quality_data,
            "total_nodes": len(nodes),
            "nodes_with_data": len(air_quality_data)
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_quality_level(score: float) -> str:
    """Convierte score numérico a nivel de calidad."""
    if score >= 80:
        return "🟢 Excelente"
    elif score >= 60:
        return "🟡 Buena"
    elif score >= 40:
        return "🟠 Moderada"
    else:
        return "🔴 Mala"