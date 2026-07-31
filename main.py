import json
import time
import argparse
import os
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
from utils import reserve, get_user_credentials

get_current_time = lambda action: time.strftime("%H:%M:%S", time.localtime(time.time() + (8 * 3600 if action else 0)))
get_current_dayofweek = lambda action: time.strftime("%A", time.localtime(time.time() + (8 * 3600 if action else 0)))

SLEEPTIME = 0.0
ENDTIME = "20:01:00"
ENABLE_SLIDER = True
MAX_ATTEMPT = 999
RESERVE_NEXT_DAY = False
FIRE_OFFSET_MS = 2.5      # 抢座偏移量（毫秒），避免被识别为脚本
FIRE_JITTER_MS = 0      # 随机抖动（毫秒），让行为更像真人

def login_and_reserve(users, usernames, passwords, action, success_list=None):
    logging.info(f"Global settings: SLEEPTIME={SLEEPTIME} ENDTIME={ENDTIME}")
    if action and len(usernames.split(",")) != len(users):
        raise Exception("user number mismatch")
    if success_list is None:
        success_list = [False] * len(users)
    cday = get_current_dayofweek(action)
    for idx, user in enumerate(users):
        username, password, times, roomid, seatid, daysofweek = user.values()
        if action:
            username = usernames.split(",")[idx]
            password = passwords.split(",")[idx]
        if cday not in daysofweek:
            continue
        if not success_list[idx]:
            logging.info(f"----- {username} {times} {seatid} -----")
            s = reserve(sleep_time=SLEEPTIME, max_attempt=MAX_ATTEMPT, enable_slider=ENABLE_SLIDER, reserve_next_day=RESERVE_NEXT_DAY)
            s.get_login_status()
            s.login(username, password)
            s.requests.headers.update({"Host": "office.chaoxing.com"})
            success_list[idx] = s.submit(times, roomid, seatid, action)
    return success_list

def main(users, action=False):
    logging.info(f"start time {get_current_time(action)}, action={'on' if action else 'off'}")
    usernames, passwords = None, None
    if action:
        usernames, passwords = get_user_credentials(action)
    success_list = None
    today_count = sum(1 for d in users if get_current_dayofweek(action) in d.get("daysofweek"))
    attempt = 0

    offset = 0.0
    try:
        r = __import__("requests").get("https://office.chaoxing.com/", timeout=5)
        if "Date" in r.headers:
            st = datetime.strptime(r.headers["Date"].replace("GMT","").strip(), "%a, %d %b %Y %H:%M:%S").timestamp()
            offset = st - time.time()
            logging.info(f"时钟偏差: {offset*1000:.0f}ms")
    except:
        logging.warning("时间校准失败")

    th, tm, ts = 19, 59, 56
    base = int(time.time() + offset)
    base = base - (base % 86400) + th * 3600 + tm * 60 + ts
    target = base - 8 * 3600
    logging.info(f"等待 {th:02d}:{tm:02d}:{ts:02d}")

    while time.time() + offset < target - 10:
        time.sleep(1)

    logging.info("预热...")
    try:
        ps = reserve(sleep_time=0, max_attempt=1, enable_slider=True, reserve_next_day=False)
        ps.get_login_status()
        u = usernames.split(",")[0] if action else users[0].get("username")
        p = passwords.split(",")[0] if action else users[0].get("password")
        ps.login(u, p)
        ps.requests.get("https://office.chaoxing.com/", timeout=5)
        logging.info("预热成功")
    except Exception as e:
        logging.warning(f"预热失败: {e}")

    remain = target - (time.time() + offset)
    if remain > 0.05:
        time.sleep(remain - 0.05)
    while time.time() + offset < target:
        pass

    # 抢座偏移：等 FIRE_OFFSET_MS 毫秒 + 随机抖动，避免太快被封号
    time.sleep((FIRE_OFFSET_MS + __import__("random").uniform(0, FIRE_JITTER_MS)) / 1000.0)
    logging.info("开抢！")

    def go():
        try:
            s = reserve(sleep_time=0, max_attempt=1, enable_slider=False, reserve_next_day=False)
            s.get_login_status()
            u = usernames.split(",")[0] if action else users[0].get("username")
            p = passwords.split(",")[0] if action else users[0].get("password")
            s.login(u, p)
            s.requests.headers.update({"Host": "office.chaoxing.com"})
            for user in users:
                _, _, times, roomid, seatid, _ = user.values()
                if s.submit(times, roomid, seatid, action):
                    return True
            return False
        except:
            return False

    with ThreadPoolExecutor(max_workers=5) as ex:
        for f in [ex.submit(go) for _ in range(5)]:
            if f.result():
                logging.info("抢座成功！")
                return

    while get_current_time(action) < ENDTIME:
        attempt += 1
        success_list = login_and_reserve(users, usernames, passwords, action, success_list)
        logging.info(f"#{attempt}")
        if sum(success_list or []) == today_count:
            logging.info("抢座成功！")
            return

def debug(users, action=False):
    if action:
        usernames, passwords = get_user_credentials(action)
    cday = get_current_dayofweek(action)
    for idx, user in enumerate(users):
        username, password, times, roomid, seatid, daysofweek = user.values()
        if type(seatid) == str:
            seatid = [seatid]
        if action:
            username = usernames.split(",")[idx]
            password = passwords.split(",")[idx]
        if cday not in daysofweek:
            continue
        s = reserve(sleep_time=SLEEPTIME, max_attempt=MAX_ATTEMPT, enable_slider=ENABLE_SLIDER, reserve_next_day=RESERVE_NEXT_DAY)
        s.get_login_status()
        s.login(username, password)
        s.requests.headers.update({"Host": "office.chaoxing.com"})
        if s.submit(times, roomid, seatid, action):
            return

def get_roomid(args1, args2):
    username = input("用户名: ")
    password = input("密码: ")
    s = reserve(sleep_time=SLEEPTIME, max_attempt=MAX_ATTEMPT, enable_slider=ENABLE_SLIDER, reserve_next_day=RESERVE_NEXT_DAY)
    s.get_login_status()
    s.login(username, password)
    s.requests.headers.update({"Host": "office.chaoxing.com"})
    s.roomid(input("deptldEnc: "))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="Chao Xing seat auto reserve")
    parser.add_argument("-u", "--user", default=os.path.join(os.path.dirname(__file__), "config.json"))
    parser.add_argument("-m", "--method", default="reserve", choices=["reserve", "debug", "room"])
    parser.add_argument("-a", "--action", action="store_true")
    args = parser.parse_args()
    with open(args.user, "r") as f:
        usersdata = json.load(f)["reserve"]
    {"reserve": main, "debug": debug, "room": get_roomid}[args.method](usersdata, args.action)
