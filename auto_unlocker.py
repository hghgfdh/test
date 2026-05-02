import hashlib
import random
import time
from datetime import datetime
import urllib3
import json

# --- Constants ---
cookie = "your_cookie_here"  # Replace with your _new_bbs_serviceToken value
feed_time_shift = 1400  # 1.4 seconds before midnight (adjust if needed)

# --- Colors (optional, for readability) ---
class Colors:
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = "\033[0m"

col_g = Colors.GREEN
col_b = Colors.BLUE
col_y = Colors.YELLOW
col_r = Colors.RED

# --- Device ID Generation ---
def generate_device_id():
    random_data = f"{random.random()}-{time.time()}"
    device_id = hashlib.sha1(random_data.encode('utf-8')).hexdigest().upper()
    return device_id

# --- Time Logic (Local Time Only) ---
def wait_until_midnight():
    now = datetime.now()
    target_time = now.replace(hour=23, minute=59, second=59, microsecond=0)  # 23:59:59 (last second before midnight)
    time_diff = (target_time - now).total_seconds()

    if time_diff <= 0:
        print(col_y + "[Info]: It's already past 23:59:59. Waiting for next midnight..." + Colors.RESET)
        target_time = now.replace(hour=23, minute=59, second=59, microsecond=0) + timedelta(days=1)
        time_diff = (target_time - now).total_seconds()

    print(col_g + f"[Waiting until]: {target_time.strftime('%H:%M:%S')}" + Colors.RESET)
    print("Do not exit the script.")

    while True:
        now = datetime.now()
        if now >= target_time:
            print(col_g + f"[Time reached]: {now.strftime('%H:%M:%S')}. Starting requests..." + Colors.RESET)
            break
        time.sleep(1)

# --- Account Status Check ---
def check_unlock_status(session, cookie_value, device_id):
    try:
        url = "https://sgp-api.buy.mi.com/bbs/api/global/user/bl-switch/state"
        headers = {
            "Cookie": f"new_bbs_serviceToken={cookie_value};versionCode=500411;versionName=5.4.11;deviceId={device_id};"
        }

        response = session.make_request('GET', url, headers=headers)
        if response is None:
            print(f"[Error] Could not retrieve unlock status.")
            return False

        response_data = json.loads(response.data.decode('utf-8'))
        response.release_conn()

        if response_data.get("code") == 100004:
            print(f"[Error] Expired Cookie. Update the `cookie` variable.")
            exit()

        data = response_data.get("data", {})
        is_pass = data.get("is_pass")
        button_state = data.get("button_state")
        deadline_format = data.get("deadline_format", "")

        if is_pass == 4:
            if button_state == 1:
                print(col_g + f"[Account Status]: Requests will be sent." + Colors.RESET)
                return True
            elif button_state == 2:
                print(col_g + f"[Account Status]: Requests blocked until {deadline_format}." + Colors.RESET)
                status_2 = input(f"Continue (" + col_b + f"Yes/No" + Colors.RESET + f")?: ")
                if status_2.lower() in ['y', 'yes']:
                    return True
                else:
                    exit()
            elif button_state == 3:
                print(col_g + f"[Account Status]: Account is less than 30 days old." + Colors.RESET)
                status_3 = input(f"Continue (" + col_b + f"Yes/No" + Colors.RESET + f")?: ")
                if status_3.lower() in ['y', 'yes']:
                    return True
                else:
                    exit()
        elif is_pass == 1:
            print(col_g + f"[Account Status]: Request approved until {deadline_format}." + Colors.RESET)
            input("Press Enter to exit...")
            exit()
        else:
            print(col_g + f"[Account Status]: Unknown state." + Colors.RESET)
            exit()
    except Exception as e:
        print(f"[Error at status checking] {e}")
        return False

# --- HTTP Session ---
class HTTP11Session:
    def __init__(self):
        self.http = urllib3.PoolManager(
            maxsize=10,
            retries=True,
            timeout=urllib3.Timeout(connect=2.0, read=15.0),
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
                preload_content=False
            )
            return response
        except Exception as e:
            print(f"[Network Error] {e}")
            return None

# --- Main Function ---
def main():
    device_id = generate_device_id()
    session = HTTP11Session()

    if check_unlock_status(session, cookie, device_id):
        wait_until_midnight()

        url = "https://sgp-api.buy.mi.com/bbs/api/global/apply/bl-auth"
        headers = {
            "Cookie": f"new_bbs_serviceToken={cookie};versionCode=500411;versionName=5.4.11;deviceId={device_id};"
        }

        try:
            while True:
                request_time = datetime.now()
                print(col_g + f"[Request]: Sent at {request_time.strftime('%H:%M:%S')}" + Colors.RESET)

                response = session.make_request('POST', url, headers=headers)
                if response is None:
                    continue

                response_time = datetime.now()
                print(col_g + f"[Response]: Received at {response_time.strftime('%H:%M:%S')}" + Colors.RESET)

                try:
                    response_data = response.data
                    response.release_conn()
                    json_response = json.loads(response_data.decode('utf-8'))
                    code = json_response.get("code")
                    data = json_response.get("data", {})

                    if code == 0:
                        apply_result = data.get("apply_result")
                        if apply_result == 1:
                            print(col_g + f"[Status]: Request approved. Checking status..." + Colors.RESET)
                            check_unlock_status(session, cookie, device_id)
                        elif apply_result == 3:
                            deadline_format = data.get("deadline_format", "Not declared")
                            print(col_g + f"[Status]: Quota reached. Retry at {deadline_format}." + Colors.RESET)
                            exit()
                        elif apply_result == 4:
                            deadline_format = data.get("deadline_format", "Not declared")
                            print(col_g + f"[Status]: Account blocked until {deadline_format}." + Colors.RESET)
                            exit()
                    elif code == 100001:
                        print(col_g + f"[Status]: Request rejected." + Colors.RESET)
                        print(col_g + f"[Response]: {json_response}" + Colors.RESET)
                    elif code == 100003:
                        print(col_g + f"[Status]: Possibly approved. Checking status..." + Colors.RESET)
                        print(col_g + f"[Response]: {json_response}" + Colors.RESET)
                        check_unlock_status(session, cookie, device_id)
                    elif code is not None:
                        print(col_g + f"[Status]: Unknown status: {code}" + Colors.RESET)
                        print(col_g + f"[Response]: {json_response}" + Colors.RESET)
                    else:
                        print(col_g + f"[Error]: No status code in response." + Colors.RESET)
                        print(col_g + f"[Response]: {json_response}" + Colors.RESET)

                except json.JSONDecodeError:
                    print(col_g + f"[Error]: JSON decode error." + Colors.RESET)
                    print(col_g + f"[Server Response]: {response_data}" + Colors.RESET)
                except Exception as e:
                    print(col_g + f"[Error processing response]: {e}" + Colors.RESET)
                    continue

        except Exception as e:
            print(col_g + f"[Request Error]: {e}" + Colors.RESET)
            exit()

if __name__ == "__main__":
    main()
