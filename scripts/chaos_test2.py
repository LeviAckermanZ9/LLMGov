# MANUAL TEST SCRIPT: Requires live Gemini/Ollama/Redis containers. Not for CI/pytest.
import urllib.request
import json
import time

URL = 'http://localhost:8000/v1/chat/completions'

def send_request(model, msg, expect_fallback=False):
    start = time.perf_counter()
    data = json.dumps({'model': model, 'messages': [{'role': 'user', 'content': msg}], 'stream': False}).encode()
    req = urllib.request.Request(URL, data=data, headers={'Content-Type': 'application/json'})
    try:
        resp = urllib.request.urlopen(req)
        body = json.loads(resp.read().decode())
        elapsed = time.perf_counter() - start
        print(f"[{elapsed:.3f}s] Response model: {body.get('model')}")
        return elapsed, body
    except Exception as e:
        elapsed = time.perf_counter() - start
        print(f"[{elapsed:.3f}s] Request failed: {e}")
        return elapsed, None

print("=== Phase 1: Tripping the breaker (CLOSED -> OPEN) ===")
# Threshold is 5. We send 5 failing requests.
for i in range(5):
    print(f"Failing Request {i+1}/5:")
    send_request('gemini/gemini-invalid', f'hello chaos {i}')

print("\n=== Phase 2: Immediate Request (OPEN) ===")
print("Sending request immediately after tripping. Should route directly to fallback with low latency.")
elapsed, body = send_request('gemini/gemini-invalid', 'fast fallback')
print(f"Latency: {elapsed:.3f}s (Proves no timeout wait)")

print("\n=== Phase 3: Wait for recovery timeout (30 seconds) ===")
print("Sleeping for 31 seconds...")
time.sleep(31)

print("\n=== Phase 4: Recovery Request (HALF_OPEN -> CLOSED) ===")
print("Sending a valid request to primary.")
elapsed, body = send_request('gemini/gemini-2.5-flash', f'hello recovery {time.time()}')
print(f"Final latency: {elapsed:.3f}s")
