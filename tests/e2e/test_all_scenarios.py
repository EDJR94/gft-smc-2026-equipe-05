import os
import requests
import json
import time

def run_tests():
    print("Iniciando testes exaustivos E2E...")
    
    data_path = os.path.join(os.path.dirname(__file__), "..", "data", "massa_testes.json")
    with open(data_path, "r", encoding="utf-8") as f:
        massa = json.load(f)
        
    scenarios = massa["test_cases"]
    success_count = 0
    
    for s in scenarios:
        print(f"\n--- Testando: {s['ticker']} - {s['description']} ---")
        try:
            res = requests.post("http://localhost:8080/analyze", json={
                "ticker": s["ticker"],
                "news_text": s["news_text"]
            })
            
            if res.status_code == 200:
                data = res.json()
                if data.get("status") == "success":
                    result = data.get("result", {})
                    sev = result.get("severity")
                    print(f"✅ Recebeu resposta: Severidade = {sev}")
                    print(f"Racional: {result.get('rationale')}")
                    
                    if sev in s["expected_severity"]:
                        print(f"🌟 SUCESSO: Severidade {sev} está de acordo com o esperado {s['expected_severity']}")
                        success_count += 1
                    else:
                        print(f"⚠️ AVISO: Agente classificou como {sev}, esperado era {s['expected_severity']}")
                else:
                    print("❌ Falha na resposta da API:", data)
            else:
                print("❌ Erro HTTP:", res.status_code, res.text)
        except Exception as e:
            print("❌ Erro de conexão:", e)
            
    print(f"\n==================================================")
    print(f"Testes finalizados: {success_count} / {len(scenarios)} passaram com excelência.")
    print(f"==================================================")

if __name__ == "__main__":
    run_tests()
