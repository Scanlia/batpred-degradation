import os
import requests
import sys
import urllib.request
import shutil
import time
print("Bootstrap Predbat")

root = "/config"

# Check if config exists, if not run locally
if not os.path.exists(root):
    root = "./"

# Download the latest Predbat release from GitHub
if not os.path.exists(root + "/apps.yaml"):
    url = "https://api.github.com/repos/springfall2008/batpred/releases"
    print("Download Predbat release list from {}".format(url))
    try:
        r = requests.get(url)
    except Exception:
        print("Error: Unable to load data from GitHub url: {}".format(url))
        print("Sleep 5 minutes before restarting")
        time.sleep(5*60)
        sys.exit(1)

    try:
        pdata = r.json()
    except requests.exceptions.JSONDecodeError:
        print("Error: Unable to decode data from GitHub url: {}".format(url))
        print("Sleep 5 minutes before restarting")
        time.sleep(5*60)
        sys.exit(1)

    tag_name = None

    if pdata and isinstance(pdata, list):
        for release in pdata:
            if not release.get("prerelease", True):
                tag_name = release.get("tag_name", "Unknown")
                break
    
    if tag_name:
        download_url = "https://github.com/springfall2008/batpred/archive/refs/tags/{}.zip".format(tag_name)
        save_path = root + "/predbat_{}.zip".format(tag_name)
        print("Downloading Predbat {}".format(download_url))

        try:
            urllib.request.urlretrieve(download_url, save_path)
            print("Predbat downloaded successfully")
        except Exception as e:
            print("Error: Unable to download Predbat - {}".format(str(e)))
            sys.exit(1)

        print("Unzipping Predbat")
        unzip_path = root + "/unzip"
        if os.path.exists(unzip_path):
            shutil.rmtree(unzip_path)
        os.makedirs(unzip_path)
        shutil.unpack_archive(save_path, unzip_path)
        unzip_path = unzip_path + "/batpred-" + tag_name.replace("v", "")
        os.system("cp {}/apps/predbat/* {}".format(unzip_path, root))
        os.system("cp {}/apps/predbat/config/* {}".format(unzip_path, root))
        os.system("rm -rf {}".format(unzip_path))
    else:
        print("Error: Unable to find a valid Predbat release")
        print("Sleep 5 minutes before restarting")
        time.sleep(5*60)
        sys.exit(1)

#
# Sync overlay files from /addon/ (Docker image) to active predbat package
# at /config/apps/predbat/.  This ensures Docker-overridden files take effect
# on every container restart, even if a previous GitHub install populated
# /config/apps/predbat/ with older versions.
#
import glob

pkg_dir = "/config/apps/predbat"
if os.path.isdir("/addon") and os.path.isdir(pkg_dir):
    synced = 0
    for f in glob.glob("/addon/*.py"):
        fname = os.path.basename(f)
        dst = os.path.join(pkg_dir, fname)
        try:
            # Only copy if source is newer or different
            if not os.path.exists(dst) or os.path.getmtime(f) > os.path.getmtime(dst):
                shutil.copy2(f, dst)
                synced += 1
        except Exception:
            pass
    if synced:
        print("Synced {} overlay file(s) from /addon/ to {}".format(synced, pkg_dir))
    # Clear stale bytecode caches so Python recompiles from the new source
    for cache_dir in [os.path.join(pkg_dir, "__pycache__"), "/addon/__pycache__"]:
        if os.path.isdir(cache_dir):
            shutil.rmtree(cache_dir)
            print("Cleared bytecode cache at {}".format(cache_dir))

#
#  UPDATED by Nic
#
print("Startup")
os.system("cd " + root + "; python3 /addon/hass.py")

print("Shutdown, sleeping 20 seconds before restarting")
time.sleep(20)
