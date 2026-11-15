"""Windows child ownership: parent exit closes a kill-on-close Job handle.

This prevents a document/LLM worker surviving an abrupt API shutdown. Handles
are not inherited; closing the parent's final handle kills the owned tree only.
"""
import ctypes
from ctypes import wintypes
import os
import subprocess


def spawn_owned(args,**kwargs):
    process=subprocess.Popen(args,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),**kwargs)
    process._workspace_job=None
    if os.name!='nt':return process
    # Native structures use pointer-sized sizes/affinity on 64-bit Windows.
    class Basic(ctypes.Structure):
        _fields_=[('process_time',ctypes.c_int64),('job_time',ctypes.c_int64),('flags',wintypes.DWORD),('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),('active',wintypes.DWORD),('affinity',ctypes.c_size_t),('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
    class Io(ctypes.Structure):
        _fields_=[(name,ctypes.c_uint64) for name in ['read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes']]
    class Extended(ctypes.Structure):
        _fields_=[('basic',Basic),('io',Io),('process_limit',ctypes.c_size_t),('job_limit',ctypes.c_size_t),('process_peak',ctypes.c_size_t),('job_peak',ctypes.c_size_t)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR];kernel.CreateJobObjectW.restype=wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE];kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    job=kernel.CreateJobObjectW(None,None);info=Extended();info.basic.flags=0x2000 # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not job or not kernel.SetInformationJobObject(job,9,ctypes.byref(info),ctypes.sizeof(info)) or not kernel.AssignProcessToJobObject(job,int(process._handle)):
        if job:kernel.CloseHandle(job)
        process.kill();process.wait(timeout=10)
        raise OSError('Owned Windows worker could not be assigned to its Job')
    process._workspace_job=job
    return process


def finish_owned(process):
    """Release the owned tree on success, timeout, cancellation or exception."""
    job=getattr(process,'_workspace_job',None)
    if job:
        kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle(job);process._workspace_job=None
    elif process.poll() is None:process.kill()
    process.wait(timeout=10)
