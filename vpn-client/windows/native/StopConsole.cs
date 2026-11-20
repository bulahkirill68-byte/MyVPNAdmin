using System;
using System.Runtime.InteropServices;
using System.Threading;
internal static class StopConsole {
 [DllImport("kernel32.dll")] static extern bool FreeConsole();
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool AttachConsole(uint pid);
 [DllImport("kernel32.dll")] static extern bool SetConsoleCtrlHandler(IntPtr handler,bool add);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool GenerateConsoleCtrlEvent(uint type,uint group);
 [STAThread] static int Main(string[] args) {
  uint pid;if(args.Length!=1||!UInt32.TryParse(args[0],out pid)||pid<4)return 2;
  FreeConsole();if(!AttachConsole(pid))return 3;
  SetConsoleCtrlHandler(IntPtr.Zero,true);
  bool ok=GenerateConsoleCtrlEvent(0,0);Thread.Sleep(400);FreeConsole();return ok?0:4;
 }
}
