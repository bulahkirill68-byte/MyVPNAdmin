using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Web.Script.Serialization;
using Microsoft.Win32;

// Short-lived native OS operations: no PowerShell startup or runtime Add-Type compilation.
internal static class RuntimeControl {
 const string RegistryPath = @"Software\Microsoft\Windows\CurrentVersion\Internet Settings";
 static readonly JavaScriptSerializer Json = new JavaScriptSerializer();
 [DllImport("wininet.dll")] static extern bool InternetSetOption(IntPtr h, int option, IntPtr buffer, int size);
 [StructLayout(LayoutKind.Sequential)] struct Security { public int length; public IntPtr descriptor; [MarshalAs(UnmanagedType.Bool)] public bool inherit; }
 [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct Startup {
  public int size; public string reserved, desktop, title; public int x,y,xSize,ySize,xCount,yCount,fill,flags; public short show,reservedSize; public IntPtr reservedPtr,input,output,error;
 }
 [StructLayout(LayoutKind.Sequential)] struct ProcessInfo { public IntPtr process,thread; public int pid,tid; }
 [StructLayout(LayoutKind.Sequential)] struct StartupEx { public Startup startup; public IntPtr attributes; }
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateFile(string path,uint access,uint share,ref Security security,uint creation,uint flags,IntPtr template);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateProcess(string executable,StringBuilder arguments,IntPtr processAttributes,IntPtr threadAttributes,bool inherit,uint flags,IntPtr environment,string directory,ref StartupEx startup,out ProcessInfo info);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool InitializeProcThreadAttributeList(IntPtr list,int count,int flags,ref IntPtr size);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool UpdateProcThreadAttribute(IntPtr list,uint flags,IntPtr attribute,IntPtr value,IntPtr size,IntPtr previous,IntPtr returned);
 [DllImport("kernel32.dll")] static extern void DeleteProcThreadAttributeList(IntPtr list);
 [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
 [DllImport("kernel32.dll")] static extern IntPtr GetStdHandle(int kind);
 [DllImport("kernel32.dll")] static extern bool SetHandleInformation(IntPtr h,uint mask,uint flags);
 static string Quote(string value) { if(value.Contains("\"")||value.Contains("\0"))throw new ArgumentException("Invalid argument"); return "\""+value+"\""; }
 static Dictionary<string,object> Read(RegistryKey key) {
  var result=new Dictionary<string,object>();
  foreach(var name in new[]{"ProxyEnable","ProxyServer","ProxyOverride","AutoConfigURL"})result[name]=key.GetValue(name,null);
  return result;
 }
 static void Refresh() { InternetSetOption(IntPtr.Zero,39,IntPtr.Zero,0); InternetSetOption(IntPtr.Zero,37,IntPtr.Zero,0); }
 static int StartCore(string[] args) {
  if(args.Length!=5)throw new ArgumentException("Invalid core arguments");
  Environment.SetEnvironmentVariable("XRAY_LOCATION_ASSET",args[4]);
  var sa=new Security{length=Marshal.SizeOf(typeof(Security)),inherit=true};
  IntPtr output=CreateFile(args[3],0x40000000,3,ref sa,2,0x80,IntPtr.Zero);
  IntPtr error=CreateFile(args[3]+".err",0x40000000,3,ref sa,2,0x80,IntPtr.Zero);
  IntPtr input=CreateFile("NUL",0x80000000,3,ref sa,3,0x80,IntPtr.Zero);
  IntPtr list=IntPtr.Zero,handles=IntPtr.Zero;
  try {
   if(output.ToInt64()==-1||error.ToInt64()==-1||input.ToInt64()==-1)throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
   var startup=new StartupEx{startup=new Startup{size=Marshal.SizeOf(typeof(StartupEx)),flags=0x101,show=0,input=input,output=output,error=error}};
   // Do not leak this command's IPC pipes into the long-lived core. Otherwise Node's
   // execFile waits for EOF until Xray exits, despite this launcher already returning.
   foreach(int kind in new[]{-10,-11,-12})SetHandleInformation(GetStdHandle(kind),1,0);
   IntPtr bytes=IntPtr.Zero;InitializeProcThreadAttributeList(IntPtr.Zero,1,0,ref bytes);
   list=Marshal.AllocHGlobal(bytes);handles=Marshal.AllocHGlobal(IntPtr.Size*3);
   if(!InitializeProcThreadAttributeList(list,1,0,ref bytes))throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
   Marshal.WriteIntPtr(handles,0,input);Marshal.WriteIntPtr(handles,IntPtr.Size,output);Marshal.WriteIntPtr(handles,IntPtr.Size*2,error);
   if(!UpdateProcThreadAttribute(list,0,new IntPtr(0x20002),handles,new IntPtr(IntPtr.Size*3),IntPtr.Zero,IntPtr.Zero))throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
   startup.attributes=list;
   ProcessInfo info;
   // Hidden NEW_CONSOLE lets StopConsole attach and request graceful TUN cleanup.
   if(!CreateProcess(args[1],new StringBuilder(Quote(args[1])+" run -config "+Quote(args[2])),IntPtr.Zero,IntPtr.Zero,true,0x80010,IntPtr.Zero,Path.GetDirectoryName(args[1]),ref startup,out info))throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
   CloseHandle(info.process);CloseHandle(info.thread);return info.pid;
  } finally { if(list!=IntPtr.Zero){DeleteProcThreadAttributeList(list);Marshal.FreeHGlobal(list);}if(handles!=IntPtr.Zero)Marshal.FreeHGlobal(handles);CloseHandle(output);CloseHandle(error);CloseHandle(input); }
 }
 static int Main(string[] args) {
  try {
   if(args.Length==0)throw new ArgumentException("Operation required");
   if(args[0]=="elevate") {
    if(args.Length<3||args.Length>4)throw new ArgumentException("Invalid helper arguments");
    var parameters=(args.Length==4?Quote(args[3])+" ":"")+"--vpn-helper "+Quote(args[2]);
    var p=Process.Start(new ProcessStartInfo(args[1],parameters){UseShellExecute=true,Verb="runas",WindowStyle=ProcessWindowStyle.Hidden});
    Console.Write(p==null?0:p.Id);return 0;
   }
   if(args[0]=="start-core"){Console.Write(StartCore(args));return 0;}
   using(var key=Registry.CurrentUser.OpenSubKey(RegistryPath,args[0]!="proxy-read")) {
    if(key==null)throw new Exception("Internet settings registry unavailable");
    if(args[0]=="proxy-read"){Console.Write(Json.Serialize(Read(key)));return 0;}
    int port;
    if(args.Length<2||!Int32.TryParse(args[1],out port)||port<1024||port>65535)throw new ArgumentException("Invalid proxy port");
    if(args[0]=="proxy-set") {
     key.SetValue("ProxyEnable",1,RegistryValueKind.DWord);key.SetValue("ProxyServer","127.0.0.1:"+port);
     key.SetValue("ProxyOverride","localhost;127.*;10.*;172.16.*;172.17.*;172.18.*;172.19.*;172.2*;172.30.*;172.31.*;192.168.*;<local>");
     key.DeleteValue("AutoConfigURL",false);
    } else if(args[0]=="proxy-restore"&&args.Length==3) {
     var current=Read(key);
     if(Convert.ToInt32(current["ProxyEnable"]??0)!=1||Convert.ToString(current["ProxyServer"])!="127.0.0.1:"+port)return 0;
     var previous=Json.Deserialize<Dictionary<string,object>>(Encoding.UTF8.GetString(Convert.FromBase64String(args[2])));
     key.SetValue("ProxyEnable",Convert.ToInt32(previous["ProxyEnable"]??0)!=0?1:0,RegistryValueKind.DWord);
     foreach(var name in new[]{"ProxyServer","ProxyOverride","AutoConfigURL"}) { if(previous[name]==null)key.DeleteValue(name,false);else key.SetValue(name,Convert.ToString(previous[name])); }
    } else throw new ArgumentException("Unknown operation");
    Refresh();return 0;
   }
  } catch(Exception e){Console.Error.Write(e.Message);return 1;}
 }
}
