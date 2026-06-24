import subprocess

def run_code(code:str,language:str='python'):
    if language == 'python':
        try:
            result = subprocess.run(['python', '-c', code],capture_output=True,text=True,timeout=5)
            return result.stdout if result.returncode == 0 else result.stderr
        except Exception as e:
            return f"Execution failed: {e}"