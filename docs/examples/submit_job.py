import requests
import time
import os

API_BASE = "http://localhost:8001/api/async/embedding"

def process_file(file_path):
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    # 1. Submit job
    print(f"📤 Submitting: {os.path.basename(file_path)}...")
    with open(file_path, 'rb') as f:
        resp = requests.post(f"{API_BASE}/submit", files={"file": f})
    
    if resp.status_code != 201:
        print(f"❌ Failed to submit: {resp.text}")
        return

    job_id = resp.json()["job_id"]
    print(f"✅ Job created: {job_id}")

    # 2. Wait for completion
    while True:
        status_resp = requests.get(f"{API_BASE}/status/{job_id}").json()
        status = status_resp["status"]
        progress = status_resp["progress"]
        
        print(f"⏳ Status: {status} ({progress}%)")
        
        if status == "done":
            break
        if status == "failed":
            print(f"❌ Job failed: {status_resp.get('error_message')}")
            return
        
        time.sleep(2)

    # 3. Get results
    print("⬇️ Downloading results...")
    result_resp = requests.get(f"{API_BASE}/result/{job_id}")
    
    # Metadata is in headers
    dim = result_resp.headers.get("X-Vector-Dim")
    chunks = result_resp.headers.get("X-Chunk-Count")
    
    output_name = f"result_{job_id}.blob"
    with open(output_name, "wb") as f:
        f.write(result_resp.content)
    
    print(f"🎉 Success! Vectors dimension: {dim}, Chunks: {chunks}")
    print(f"💾 Result saved to: {output_name}")

if __name__ == "__main__":
    # Example usage
    # process_file("path/to/your/document.txt")
    print("Tip: Call process_file('your_file.txt') to test.")
