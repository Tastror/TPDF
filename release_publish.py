"""TPDF 一键 GitHub Release 发布脚本。

前置条件
--------
- 已安装 GitHub CLI (`gh`)：https://cli.github.com/
  Windows: `winget install --id GitHub.cli`
  macOS:   `brew install gh`
  Linux:   参考官网
- 已登录：`gh auth login`
- 当前目录是 TPDF 仓库，已配置好 `origin` 远端
- `dist/release/` 下已经有当前版本的产物（由 `release_build.py` 生成）

脚本会做的事
-----------
1. 从 `pyproject.toml` 读取版本号 → 派生 tag `v{version}`
2. 校验工作区状态（默认要求干净，可用 `--allow-dirty` 跳过）
3. 校验 `dist/release/` 下是否有当前版本的产物
4. 若本地无 `v{version}` tag，则创建并推送到 origin
5. 若 release 不存在，执行 `gh release create --generate-notes` 并上传所有产物
   （默认包含 `.sha256` 校验文件；可用 `--no-sha256` 关闭）
6. 若 release 已存在（比如在另一个平台补充产物），执行 `gh release upload --clobber`
7. 打印 release 的网页 URL

用法
----
    python release_publish.py                      # 正式发布
    python release_publish.py --draft              # 发布为草稿（不对外可见）
    python release_publish.py --prerelease         # 标记为预发布
    python release_publish.py --notes-file NOTES.md  # 用文件作为 release notes
    python release_publish.py --notes "..."        # 直接给一段 notes（不再使用 --generate-notes）
    python release_publish.py --allow-dirty        # 允许工作区未提交
    python release_publish.py --no-sha256          # 不上传 .sha256 校验文件
    python release_publish.py --yes                # 跳过交互确认
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
PYPROJECT = ROOT / "pyproject.toml"
RELEASE_DIR = ROOT / "dist" / "release"


def read_version() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    if not m:
        print("错误：无法从 pyproject.toml 读取 version。", file=sys.stderr)
        sys.exit(1)
    return m.group(1)


def check_tools() -> None:
    if shutil.which("git") is None:
        print("错误：未找到 `git`。", file=sys.stderr)
        sys.exit(1)
    if shutil.which("gh") is None:
        print(
            "错误：未找到 GitHub CLI (`gh`)。请先安装并登录：\n"
            "  Windows:  winget install --id GitHub.cli\n"
            "  macOS:    brew install gh\n"
            "  Linux:    参考 https://cli.github.com/\n"
            "然后执行：gh auth login",
            file=sys.stderr,
        )
        sys.exit(1)


def run(cmd: list[str], *, check: bool = True,
        capture: bool = False) -> subprocess.CompletedProcess:
    if not capture:
        print("▶", " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=capture,
    )
    if check and result.returncode != 0:
        if capture:
            sys.stderr.write(result.stdout or "")
            sys.stderr.write(result.stderr or "")
        sys.exit(result.returncode)
    return result


def git_is_clean() -> bool:
    r = run(["git", "status", "--porcelain"], capture=True)
    return r.stdout.strip() == ""


def local_tag_exists(tag: str) -> bool:
    r = run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}"],
            check=False, capture=True)
    return r.returncode == 0


def remote_tag_exists(tag: str) -> bool:
    r = run(["git", "ls-remote", "--tags", "origin", tag], capture=True)
    return bool(r.stdout.strip())


def fetch_remote_tag(tag: str) -> bool:
    """尝试把远端 tag 拉到本地。成功返回 True。"""
    r = run(["git", "fetch", "origin", "tag", tag, "--no-tags"],
            check=False, capture=True)
    return r.returncode == 0 and local_tag_exists(tag)


def head_commit() -> str:
    r = run(["git", "rev-parse", "HEAD"], capture=True)
    return r.stdout.strip()


def tag_commit(tag: str) -> str | None:
    """返回 tag 指向的 commit SHA（annotated tag 会被解引用到目标 commit）。"""
    r = run(["git", "rev-list", "-n", "1", tag], check=False, capture=True)
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


def release_exists(tag: str) -> bool:
    r = run(["gh", "release", "view", tag, "--json", "tagName"],
            check=False, capture=True)
    return r.returncode == 0


def release_url(tag: str) -> str:
    r = run(["gh", "release", "view", tag, "--json", "url"],
            check=False, capture=True)
    if r.returncode != 0:
        return ""
    try:
        return json.loads(r.stdout).get("url", "")
    except json.JSONDecodeError:
        return ""


def collect_artifacts(version: str, include_sha: bool) -> list[Path]:
    if not RELEASE_DIR.exists():
        print(f"错误：{RELEASE_DIR} 不存在。请先运行 `python release_build.py --clean`。",
              file=sys.stderr)
        sys.exit(1)

    prefix = f"TPDF-v{version}-"
    # 收集主产物（排除 .sha256）
    main = sorted(
        p for p in RELEASE_DIR.iterdir()
        if p.is_file() and p.name.startswith(prefix) and not p.name.endswith(".sha256")
    )
    if not main:
        print(f"错误：{RELEASE_DIR} 下没有匹配 `{prefix}*` 的产物。", file=sys.stderr)
        print("提示：先在每个目标平台上运行 `python release_build.py --clean`。",
              file=sys.stderr)
        sys.exit(1)

    sha = []
    if include_sha:
        sha = sorted(
            p for p in RELEASE_DIR.iterdir()
            if p.is_file() and p.name.startswith(prefix) and p.name.endswith(".sha256")
        )

    return main + sha


def confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    try:
        ans = input(f"{prompt} [y/N] ").strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


def main() -> int:
    ap = argparse.ArgumentParser(description="一键发布 TPDF 到 GitHub Release")
    ap.add_argument("--draft", action="store_true", help="发布为草稿")
    ap.add_argument("--prerelease", action="store_true", help="标记为预发布")
    ap.add_argument("--notes", help="自定义 release notes（字符串）")
    ap.add_argument("--notes-file", help="使用文件内容作为 release notes")
    ap.add_argument("--allow-dirty", action="store_true",
                    help="允许工作区有未提交修改（产物可能与 tag commit 不一致）")
    ap.add_argument("--allow-mismatch", action="store_true",
                    help="补发时允许 HEAD 与 tag 指向的 commit 不一致（强烈不推荐）")
    ap.add_argument("--no-sha256", action="store_true",
                    help="不上传 .sha256 校验文件")
    ap.add_argument("--yes", "-y", action="store_true",
                    help="跳过所有交互确认")
    args = ap.parse_args()

    check_tools()

    version = read_version()
    tag = f"v{version}"
    title = f"TPDF {tag}"

    print(f"▶ 版本：{version}   tag：{tag}")

    # 1. 先识别本次属于"首发"还是"补发"
    #    - tag 不存在 → 首发（需要打 tag、推 tag → 要求 HEAD 正确 + 工作区干净）
    #    - tag 已存在（本地或远端） → 补发（纯上传，不碰 git，工作区随便）
    has_local_tag = local_tag_exists(tag)
    has_remote_tag = remote_tag_exists(tag)

    if not has_local_tag and has_remote_tag:
        print(f"▶ 远端已有 tag {tag}，本地没有，尝试 fetch 下来。")
        if fetch_remote_tag(tag):
            has_local_tag = True
        else:
            print(f"警告：fetch tag {tag} 失败，稍后会在当前 HEAD 尝试创建。",
                  file=sys.stderr)

    tag_already_exists = has_local_tag or has_remote_tag
    is_new_tag = not tag_already_exists

    if is_new_tag:
        print(f"▶ 首发模式：tag {tag} 不存在，将在当前 HEAD ({head_commit()[:7]}) 上创建。")
    else:
        # 补发：必须验证 HEAD 与 tag 指向的 commit 一致，
        # 否则这次 build 出来的产物和已发布的来自不同 commit，release 里会混着两份代码。
        tag_sha = tag_commit(tag)
        head_sha = head_commit()
        if tag_sha is None:
            print(f"错误：无法解析 tag {tag} 指向的 commit。", file=sys.stderr)
            return 1
        if head_sha != tag_sha:
            msg = (f"错误：HEAD ({head_sha[:7]}) 与 tag {tag} 指向的 commit "
                   f"({tag_sha[:7]}) 不一致。\n"
                   f"      同一个 release 的不同平台产物必须来自同一个 commit，"
                   f"否则二进制会对不上。\n"
                   f"      解决：\n"
                   f"        git checkout {tag}\n"
                   f"        uv run --extra build python release_build.py --clean\n"
                   f"        python release_publish.py\n"
                   f"      如果你非常清楚自己在做什么，可以加 `--allow-mismatch` 跳过。")
            if not args.allow_mismatch:
                print(msg, file=sys.stderr)
                return 1
            print("⚠ HEAD 与 tag commit 不一致（--allow-mismatch 已启用）。", file=sys.stderr)
        else:
            print(f"▶ 补发模式：HEAD 与 tag {tag} 一致 ({head_sha[:7]})。")

    # 工作区必须干净（产物否则不对应任何 commit）
    if not git_is_clean():
        if not args.allow_dirty:
            print("错误：工作区存在未提交的修改，产物将无法对应任何 commit。\n"
                  "      请先 commit / stash，或加 `--allow-dirty` 跳过。",
                  file=sys.stderr)
            return 1
        print("⚠ 工作区未清理（--allow-dirty 已启用）。")

    # 2. 收集产物
    artifacts = collect_artifacts(version, include_sha=not args.no_sha256)
    print("▶ 待上传产物：")
    for p in artifacts:
        size_mb = p.stat().st_size / 1024 / 1024
        print(f"    {p.name}    ({size_mb:.1f} MB)")

    # 3. 交互确认
    mode = []
    if args.draft:
        mode.append("草稿")
    if args.prerelease:
        mode.append("预发布")
    if not is_new_tag:
        mode.append("补发")
    mode_str = f"（{' + '.join(mode)}）" if mode else ""
    if not confirm(f"确认发布 {title}{mode_str} 到 GitHub？", args.yes):
        print("已取消。")
        return 1

    # 4. tag 处理（仅首发路径需要）
    if is_new_tag:
        run(["git", "tag", "-a", tag, "-m", title])
        run(["git", "push", "origin", tag])
    else:
        if not has_remote_tag:
            # 极少见：远端没 tag 但本地有（比如上次推送失败）
            run(["git", "push", "origin", tag])

    # 5. create or upload
    artifact_paths = [str(p) for p in artifacts]

    if release_exists(tag):
        print(f"▶ Release {tag} 已存在，使用 upload --clobber 追加产物。")
        run(["gh", "release", "upload", tag, *artifact_paths, "--clobber"])
    else:
        create_cmd = [
            "gh", "release", "create", tag,
            *artifact_paths,
            "--title", title,
        ]
        if args.notes_file:
            create_cmd += ["--notes-file", args.notes_file]
        elif args.notes:
            create_cmd += ["--notes", args.notes]
        else:
            create_cmd += ["--generate-notes"]
        if args.draft:
            create_cmd += ["--draft"]
        if args.prerelease:
            create_cmd += ["--prerelease"]
        run(create_cmd)

    url = release_url(tag)
    print("\n✓ 发布完成。")
    if url:
        print(f"  {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
