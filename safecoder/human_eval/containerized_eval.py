import os
import json
import tempfile
import subprocess
from pathlib import Path
from .problem_yaml import Problem, Result, ResultList, TestResults

# Python evaluation function
def eval_script_python(path: Path) -> dict:
    try:
        # Run the Python script; exit code 0 indicates success
        output = subprocess.run(
            ["python3", str(path)],
            encoding="utf-8",
            capture_output=True,
            timeout=5
        )
        returncode = output.returncode
        status = "OK" if returncode == 0 else "SyntaxError"
    except subprocess.TimeoutExpired as exc:
        # Execution timed out
        return {
            "status": "Timeout",
            "exit_code": -1,
            "stdout": "",
            "stderr": "Python execution timed out",
        }
    # Build result dict
    dict_result = {
        "status": status,
        "exit_code": returncode,
        "stdout": str(getattr(output, "stdout", "")),
        "stderr": str(getattr(output, "stderr", "")),
    }
    return dict_result

# Java evaluation function
def eval_script_java(path: Path) -> dict:
    code = path.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        java_file = td / "Main.java"
        java_file.write_text(code, encoding="utf-8")
        # Compile Java file
        try:
            cp = subprocess.run(
                ["javac", "Main.java"],
                cwd=td,
                capture_output=True,
                text=True,
                timeout=5
            )
            if cp.returncode != 0:
                return {
                    "status": "CompileError",
                    "exit_code": cp.returncode,
                    "stdout": cp.stdout,
                    "stderr": cp.stderr,
                }
        except subprocess.TimeoutExpired:
            return {
                "status": "CompileTimeout",
                "exit_code": -1,
                "stdout": "",
                "stderr": "javac timed out",
            }
        # Run Java class
        try:
            rp = subprocess.run(
                ["java", "-cp", str(td), "Main"],
                cwd=td,
                capture_output=True,
                text=True,
                timeout=5
            )
            return {
                "status": "OK" if rp.returncode == 0 else "RuntimeError",
                "exit_code": rp.returncode,
                "stdout": rp.stdout,
                "stderr": rp.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "Timeout",
                "exit_code": -1,
                "stdout": "",
                "stderr": "java execution timed out",
            }

# C++ evaluation function
#edit
def eval_script_cpp(path: Path) -> dict:
    # 读取完整 C++ 源码（用户代码 + 测试 Harness）
    code = path.read_text(encoding="utf-8")

    # 按 "#undef NDEBUG" 切分，避免误分割用户定义的 main
    test_marker = "#undef NDEBUG"
    split_idx = code.find(test_marker)
    if split_idx != -1:
        user_code = code[:split_idx]
        test_code = code[split_idx:]
    else:
        user_code = code
        test_code = ""

    #edit: 去除顶部多行注释（docstring），避免残留示例行导致编译错误
    start = user_code.find("/*")
    end = user_code.find("*/", start+2)
    if start != -1 and end != -1:
        user_code = user_code[:start] + user_code[end+2:]
    #edit end

    # 删除用户代码中多余的 main 定义，只保留函数实现
    main_idx = user_code.find("int main")
    if main_idx != -1:
        user_code = user_code[:main_idx]

    # 读取完整 C++ 源码（用户代码 + 测试 Harness）
    code = path.read_text(encoding="utf-8")

    # 按 "#undef NDEBUG" 切分，避免误分割用户定义的 main
    test_marker = "#undef NDEBUG"
    split_idx = code.find(test_marker)
    if split_idx != -1:
        user_code = code[:split_idx]
        test_code = code[split_idx:]
    else:
        user_code = code
        test_code = ""

    # 删除用户代码中多余的 main 定义，只保留函数实现
    main_idx = user_code.find("int main")
    if main_idx != -1:
        user_code = user_code[:main_idx]

    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        # 写入用户代码
        user_file = td / "user.cpp"
        user_file.write_text(user_code, encoding="utf-8")
        files_to_compile = [str(user_file)]

        # 如果存在测试代码，写入 test.cpp 并加入编译列表
        if test_code:
            # 去除测试代码中可能残留的 doc 例子行
            sanitized_lines = []
            for line in test_code.splitlines():
                if not line.strip().startswith('>>>'):
                    sanitized_lines.append(line)
            test_code = "\n".join(sanitized_lines) + "\n"

            # 自动提取用户函数签名，用于测试文件的 extern 声明
            sig_decl = ''
            brace_idx = user_code.find('{')
            if brace_idx != -1:
                before = user_code[:brace_idx]
                for line in reversed(before.splitlines()):
                    line = line.strip()
                    if line and not line.startswith('//'):
                        sig_decl = line.rstrip() + ';'
                        break

            # 动态提取 include 和 using 语句
            include_lines = []
            for line in user_code.splitlines():
                stripped = line.strip()
                if stripped.startswith("#include") or stripped.startswith("using namespace"):
                    include_lines.append(stripped)
            # 确保测试文件有 assert 声明
            if not any('#include <cassert>' in inc for inc in include_lines):
                include_lines.insert(0, "#include <cassert>")
            includes = "\n".join(include_lines) + "\n" + f"{sig_decl}\n"

            test_file = td / "test.cpp"
            test_file.write_text(includes + test_code, encoding="utf-8")
            files_to_compile.append(str(test_file))

        exe = td / "exe"
        # 编译用户代码与测试代码
        try:
            cp = subprocess.run(
                ["g++", "-std=c++17", *files_to_compile, "-o", str(exe)],
                cwd=td,
                capture_output=True,
                text=True,
                timeout=5
            )
            if cp.returncode != 0:
                return {
                    "status": "CompileError",
                    "exit_code": cp.returncode,
                    "stdout": cp.stdout,
                    "stderr": cp.stderr,
                }
        except subprocess.TimeoutExpired:
            return {
                "status": "CompileTimeout",
                "exit_code": -1,
                "stdout": "",
                "stderr": "g++ timed out",
            }

        # 运行可执行文件并捕获结果
        try:
            rp = subprocess.run(
                [str(exe)],
                cwd=td,
                capture_output=True,
                text=True,
                timeout=5
            )
            return {
                "status": "OK" if rp.returncode == 0 else "RuntimeError",
                "exit_code": rp.returncode,
                "stdout": rp.stdout,
                "stderr": rp.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "Timeout",
                "exit_code": -1,
                "stdout": "",
                "stderr": "C++ execution timed out",
            }

#edit end

# Dispatch function for different languages
def eval_string_script(language, program):
    lang = language.lower()
    if lang == 'py':
        eval_func, file_ext = eval_script_python, '.py'
    elif lang == 'java':
        eval_func, file_ext = eval_script_java, '.java'
    elif lang in ('c++', 'cpp'):
        eval_func, file_ext = eval_script_cpp, '.cpp'
    else:
        raise ValueError(f"Unsupported language: {language}")
    with tempfile.NamedTemporaryFile(suffix=file_ext, delete=True) as f:
        f.write(program.encode('utf-8'))
        f.flush()
        result = eval_func(Path(f.name))
    # Normalize stdout/stderr
    if isinstance(result.get("stdout"), (bytes, bytearray)):
        result["stdout"] = result["stdout"].decode("utf-8", errors="ignore")
    if result.get("stdout") is None:
        result["stdout"] = ""
    if result.get("stderr") is None:
        result["stderr"] = ""
    if isinstance(result.get("stderr"), (bytes, bytearray)):
        result["stderr"] = result["stderr"].decode("utf-8", errors="ignore")
    return {
        'program': program,
        'stdout': result["stdout"][:2048],
        'stderr': result["stderr"][:2048],
        'exit_code': result.get('exit_code', -1),
        'status': result.get('status', 'Error'),
    }
