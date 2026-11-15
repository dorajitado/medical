import argparse
from .native_imaging import ROOT, configure, launch

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--qa',action='store_true')
    args=parser.parse_args()
    config=configure(ROOT/'data'/('qa-imaging' if args.qa else 'imaging'),8043 if args.qa else 8042,8001 if args.qa else 8000)
    process=launch(config)
    print('Windows native Orthanc/OHIF ready. Ctrl+C to stop.',flush=True)
    try:
        process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait(timeout=10)
