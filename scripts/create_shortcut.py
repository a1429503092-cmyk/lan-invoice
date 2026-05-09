import os, sys

script = r'c:\Users\dell\WorkBuddy\20260425180357\src\invoice_tool.py'
python_exe = sys.executable
desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
lnk_path = os.path.join(desktop, '发票归档.lnk')

try:
    import win32com.client
    shell = win32com.client.Dispatch('WScript.Shell')
    shortcut = shell.CreateShortCut(lnk_path)
    shortcut.TargetPath = python_exe
    shortcut.Arguments = '"' + script + '"'
    shortcut.WorkingDirectory = os.path.dirname(script)
    shortcut.Description = '发票归档工具'
    shortcut.Save()
    print('OK:' + lnk_path)
except ImportError:
    print('NO_WIN32COM')
except Exception as e:
    print('FAIL:' + str(e))
