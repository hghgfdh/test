import hashlib
import random
import time
import threading
from datetime import datetime, timedelta
import urllib3
import json
import os

# --- Configuration ---
target = "59:59"  # Target time in "MM:SS" format
cookie_file = "cookies.txt"  # File with one cookie per line
feed_time_shift = 1400  # Start 1400ms before target
request_interval = 1000  # 1000ms between requests
stop_after = 2500  # Stop 2500ms after target
request_timeout = 5  # Timeout for individual requests (seconds)

# --- Colors (optional) ---
class Colors:
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    RESET = "\033[0m"

col_g = Colors.GREEN
col_b = Colors.BLUE
col_y = Colors.YELLOW
col_r = Colors.RED
col_c = Colors.CYAN

# --- Global Variables ---
valid_cookies = []  # Stores valid cookies
results = {}  # Stores results for each request
lock = threading.Lock()  # Thread-safe lock for results

# --- Device ID Generation ---
def generate_device_id():
    random_data = f"{random.random()}-{time.time()}-{os.urandom(4).hex()}"
    return hashlib.sha1(random_data.encode('utf-8')).hexdigest().upper()

# --- Read Cookies from File ---
def read_cookies():
    if not os.path.exists(cookie_file):
        print(col_r + f"[Error]: File '{cookie_file}' does not exist in the current directory." + Colors.RESET)
        print(col_y + f"[Info]: Current directory: {os.getcwd()}" + Colors.RESET)
        print(col_y + f"[Info]: Expected file: {os.path.abspath(cookie_file)}" + Colors.RESET)
        exit()

    with open(cookie_file, "r") as f:
        lines = f.readlines()

    total_lines = len(lines)
    print(col_y + f"[File Info]: '{cookie_file}' exists with {total_lines} total lines." + Colors.RESET)

    # Filter out empty lines and comments (lines starting with #)
    cookies = []
    for line in lines:
        stripped_line = line.strip()
        if stripped_line and not stripped_line.startswith("#"):
            cookies.append(stripped_line)

    num_cookies = len(cookies)
    print(col_y + f"[File Info]: Loaded {num_cookies} cookies (ignored {total_lines - num_cookies} empty/comment lines)." + Colors.RESET)

    if num_cookies == 0:
        print(col_r + "[Error]: No valid cookies found in the file. Add one cookie per line (ignore lines starting with #)." + Colors.RESET)
        exit()

    return cookies

# --- Check Cookie Status ---
def check_cookie_status(session, cookie_value):
    try:
        url = "https://sgp-api.buy.mi.com/bbs/api/global/user/bl-switch/state"
        device_id = generate_device_id()
        headers = {
            "Cookie": f"new_bbs_serviceToken={cookie_value};versionCode=500411;versionName=5.4.11;deviceId={device_id};"
        }
        response = session.make_request('GET', url, headers=headers)
        if response is None:
            return False, "Request failed"

        response_data = json.loads(response.data.decode('utf-8'))
        response.release_conn()

        if response_data.get("code") == 100004:
            return False, "Expired cookie"

        data = response_data.get("data", {})
        is_pass = data.get("is_pass")
        button_state = data.get("button_state")
        deadline_format = data.get("deadline_format", "N/A")

        if is_pass == 4 and button_state == 1:
            return True, "Ready"
        elif is_pass == 1:
            return False, f"Already approved (until {deadline_format})"
        elif button_state == 2:
            return False, f"Blocked until {deadline_format}"
        elif button_state == 3:
            return False, "Account <30 days old"
        else:
            return False, f"Unknown state (is_pass={is_pass}, button_state={button_state})"

    except Exception as e:
        return False, f"Error: {str(e)}"

# --- Print Cookie Statuses ---
def print_cookie_statuses(cookies, valid_cookies, statuses):
    print("\n" + col_c + "=== Cookie Status Summary ===" + Colors.RESET)
    print(f"{col_y}[Total Cookies Detected]: {len(cookies)}{Colors.RESET}")
    print(f"{col_g}[Valid Cookies]: {len(valid_cookies)}{Colors.RESET}")
    print(f"{col_r}[Invalid Cookies]: {len(cookies) - len(valid_cookies)}{Colors.RESET}\n")

    print(col_b + "--- Individual Cookie Statuses ---" + Colors.RESET)
    for i, (cookie, status) in enumerate(zip(cookies, statuses), 1):
        short_cookie = f"{cookie[:10]}..." if len(cookie) > 10 else cookie
        is_valid = "✅" if cookie in valid_cookies else "❌"
        print(f"{i}. {is_valid} {short_cookie}: {status}")

    print()

# --- HTTP Session ---
class HTTP11Session:
    def __init__(self):
        self.http = urllib3.PoolManager(
            maxsize=20,
            retries=True,
            timeout=urllib3.Timeout(connect=2.0, read=request_timeout),
            headers={}
        )

    def make_request(self, method, url, headers=None, body=None):
        try:
            request_headers = {}
            if headers:
                request_headers.update(headers)
                request_headers['Content-Type'] = 'application/json; charset=utf-8'

            if method == 'POST':
                if body is None:
                    body = '{"is_retry":true}'.encode('utf-8')
                request_headers['Content-Length'] = str(len(body))
                request_headers['Accept-Encoding'] = 'gzip, deflate, br'
                request_headers['User-Agent'] = 'okhttp/4.12.0'
                request_headers['Connection'] = 'keep-alive'

            response = self.http.request(
                method,
                url,
                headers=request_headers,
                body=body,
                preload_content=False,
                timeout=request_timeout
            )
            return response
        except Exception as e:
            return None

# --- Send Request (Non-blocking) ---
def send_request(session, cookie_value, request_time):
    device_id = generate_device_id()
    url = "https://sgp-api.buy.mi.com/bbs/api/global/apply/bl-auth"
    headers = {
        "Cookie": f"new_bbs_serviceToken={cookie_value};versionCode=500411;versionName=5.4.11;deviceId={device_id};"
    }

    try:
        response = session.make_request('POST', url, headers=headers)
        if response:
            response_data = json.loads(response.data.decode('utf-8'))
            response.release_conn()
            code = response_data.get("code")
            data = response_data.get("data", {})

            with lock:
                results[cookie_value] = {
                    "time": request_time.strftime('%H:%M:%S'),
                    "device_id": device_id,
                    "code": code,
                    "data": data,
                    "status": "Success"
                }
    except Exception as e:
        with lock:
            results[cookie_value] = {
                "time": request_time.strftime('%H:%M:%S'),
                "device_id": device_id,
                "error": str(e),
                "status": "Failed"
            }

# --- Time Logic ---
def wait_until_feed_time():
    target_min, target_sec = map(int, target.split(":"))
    while True:
        now = datetime.now()
        if now.minute == target_min and now.second == target_sec:
            # Calculate feed_time_shift (1400ms before target)
            feed_time = now - timedelta(milliseconds=feed_time_shift)
            if now >= feed_time:
                print(col_g + f"[Feed Time Reached]: Starting requests at {now.strftime('%H:%M:%S')}" + Colors.RESET)
                return
        time.sleep(0.1)

# --- Main Loop ---
def main_loop(session):
    start_time = datetime.now()
    target_min, target_sec = map(int, target.split(":"))
    stop_time = start_time.replace(minute=target_min, second=target_sec) + timedelta(milliseconds=stop_after)

    index = 0
    while datetime.now() < stop_time:
        if index >= len(valid_cookies):
            index = 0  # Loop back to the first cookie

        cookie = valid_cookies[index]
        request_time = datetime.now()
        threading.Thread(
            target=send_request,
            args=(session, cookie, request_time),
            daemon=True
        ).start()

        index += 1
        time.sleep(request_interval / 1000)  # Convert ms to seconds

# --- Print Results ---
def print_results():
    print("\n" + col_c + "=== Request Results ===" + Colors.RESET)
    if not results:
        print(col_y + "[No results to display]" + Colors.RESET)
        return

    for i, (cookie, result) in enumerate(results.items(), 1):
        short_cookie = f"{cookie[:10]}..." if len(cookie) > 10 else cookie
        status = result.get("status", "Unknown")
        time_sent = result.get("time", "N/A")
        device_id = result.get("device_id", "N/A")[:8] + "..."
        code = result.get("code", "N/A")
        error = result.get("error", "None")

        print(
            f"{i}. {col_b}[Cookie]: {short_cookie}{Colors.RESET} "
            f"{col_g}[Time]: {time_sent}{Colors.RESET} "
            f"{col_y}[Device ID]: {device_id}{Colors.RESET} "
            f"{col_c}[Status]: {status}{Colors.RESET} "
            f"{col_y}[Code]: {code}{Colors.RESET}"
        )
        if error != "None":
            print(f"   {col_r}[Error]: {error}{Colors.RESET}")

# --- Main Function ---
def main():
    global valid_cookies

    # Read cookies from file
    cookies = read_cookies()

    # Initialize session
    session = HTTP11Session()

    # Check all cookies
    print(col_y + "[Checking Cookie Statuses...]" + Colors.RESET)
    statuses = []
    for cookie in cookies:
        is_valid, status = check_cookie_status(session, cookie)
        statuses.append(status)
        if is_valid:
            valid_cookies.append(cookie)

    # Print cookie statuses
    print_cookie_statuses(cookies, valid_cookies, statuses)

    if not valid_cookies:
        print(col_r + "[Error]: No valid cookies found. Exiting." + Colors.RESET)
        exit()

    # Wait until feed_time_shift before target
    wait_until_feed_time()

    # Start main loop
    main_loop(session)

    # Wait for all threads to finish
    time.sleep(1)

    # Print results
    print_results()

if __name__ == "__main__":
    main()
