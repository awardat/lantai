"""GitHub 推送前安全扫描：敏感文件名 / 硬编码密钥 / 忽略覆盖。"""
import re
import subprocess

files = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout.split()
print("=== 已跟踪文件数:", len(files))

sensitive_names = [
    f for f in files
    if re.search(r"\.env|secret|credential|\.pem|\.key$|\.p12|id_rsa", f, re.I)
]
print("=== 敏感文件名:", sensitive_names if sensitive_names else "无")

pat = re.compile(
    r"sk-[A-Za-z0-9]{20,}"
    r"|api[_-]?key\s*[:=]\s*[\"']?[A-Za-z0-9]{16,}"
    r"|bearer\s+[A-Za-z0-9._-]{16,}"
    r"|password\s*=\s*[\"']?[^\"'\s]{8,}"
    r"|AKIA[0-9A-Z]{16}",
    re.I,
)
code = [f for f in files if not re.search(r"\.(md|txt)$", f)]
hits = []
for f in code:
    try:
        text = open(f, encoding="utf-8", errors="ignore").read()
        for m in pat.finditer(text):
            hits.append((f, m.group(0)[:48]))
    except Exception:
        pass
print("=== 代码硬编码敏感值:", hits if hits else "无")

ignored = subprocess.run(
    ["git", "check-ignore", "shell/node_modules", "shell/src-tauri/target",
     "shell/ui/dist", "backend/data", "release", "shell/.npmrc"],
    capture_output=True, text=True,
).stdout.strip().split("\n")
print("=== gitignore 覆盖:", [i for i in ignored if i])

print("=== 工作区状态 ===")
print(subprocess.run(["git", "status", "--short"], capture_output=True, text=True).stdout)

print("=== 提交历史作者 ===")
print(subprocess.run(["git", "log", "--format=%an <%ae>", "-3"], capture_output=True, text=True).stdout)
