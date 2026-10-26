#!/usr/bin/env python3
"""YouTube resumable uploader. Creds read via the 1Password CLI `op` at runtime
(env OP_VAULT, OP_YT_CLIENT_ITEM [username=client_id,password=client_secret], OP_YT_REFRESH_ITEM [field credential]).
  yt_upload.py --check                      # read-only: mint token, show channel
  yt_upload.py FILE --title T [--description D] [--tags a,b] [--privacy private|unlisted|public] [--category 10]
Default privacy is private."""
import argparse, json, os, subprocess, sys, urllib.request, urllib.parse

def op(item, field):
    return subprocess.check_output(["op","item","get",item,"--vault",os.environ["OP_VAULT"],"--fields",field,"--reveal"],text=True).strip()

def access_token():
    cid = op(os.environ["OP_YT_CLIENT_ITEM"], "username")
    sec = op(os.environ["OP_YT_CLIENT_ITEM"], "password")
    rt  = op(os.environ["OP_YT_REFRESH_ITEM"], "credential")
    d = urllib.parse.urlencode(dict(client_id=cid, client_secret=sec, refresh_token=rt, grant_type="refresh_token")).encode()
    r = json.load(urllib.request.urlopen("https://oauth2.googleapis.com/token", d))
    return r["access_token"], r.get("scope", "")

def req(method, url, tok, data=None, headers=None):
    h = {"Authorization": "Bearer " + tok, **(headers or {})}
    return urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h, method=method))

def upload(tok, path, meta, chunk=8 << 20):
    size = os.path.getsize(path)
    r = req("POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", tok,
            json.dumps(meta).encode(), {"Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(size), "X-Upload-Content-Type": "video/*"})
    loc = r.headers["Location"]; off = 0
    with open(path, "rb") as f:
        while off < size:
            f.seek(off); buf = f.read(chunk); end = off + len(buf) - 1
            try:
                resp = req("PUT", loc, tok, buf, {"Content-Range": f"bytes {off}-{end}/{size}"})
                return json.load(resp)
            except urllib.error.HTTPError as e:
                if e.code != 308: raise
                rng = e.headers.get("Range"); off = int(rng.split("-")[1]) + 1 if rng else 0
                print(f"  {off*100//size}%", file=sys.stderr)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?"); ap.add_argument("--check", action="store_true")
    ap.add_argument("--title"); ap.add_argument("--description", default=""); ap.add_argument("--tags", default="")
    ap.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"]); ap.add_argument("--category", default="10")
    a = ap.parse_args()
    tok, scope = access_token()
    if a.check:
        ch = json.load(req("GET", "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true", tok))
        print("scopes:", scope); [print("channel:", i["id"], i["snippet"]["title"]) for i in ch.get("items", [])]; sys.exit()
    if not (a.file and a.title): ap.error("FILE and --title required")
    meta = {"snippet": {"title": a.title, "description": a.description, "categoryId": a.category,
            "tags": [t.strip() for t in a.tags.split(",") if t.strip()]}, "status": {"privacyStatus": a.privacy, "selfDeclaredMadeForKids": False}}
    v = upload(tok, a.file, meta)
    print("uploaded:", v["id"], "https://youtu.be/" + v["id"], v["status"]["privacyStatus"])
