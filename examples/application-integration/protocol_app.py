"""Example: call the versioned application protocol without a shell."""
import json
import subprocess
import sys
from pathlib import Path


def call_harness(executable, operation, arguments):
    # Set the harness's cooperative deadline; an application may additionally supervise
    # the whole process tree for a hard native-validator deadline.
    process=subprocess.run([executable,operation,*arguments],capture_output=True,text=True,check=False)
    result=json.loads(process.stdout)
    if result['schema_version']!='1.0' or result['exit_code']!=process.returncode:
        raise ValueError('Unsupported protocol or inconsistent exit code')
    return result,process.stderr


if __name__=='__main__':
    request=json.loads(Path(sys.argv[1]).read_text())
    result,diagnostics=call_harness(request['harness'],request['operation'],request['arguments'])
    print(json.dumps(result,indent=2))
    if diagnostics:print(diagnostics,file=sys.stderr,end='')
    sys.exit(result['exit_code'])
