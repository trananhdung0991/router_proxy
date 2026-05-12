import os
import sys


def get_resource_path(resource_path, use_realpath=False):
    if use_realpath:
        if getattr(sys, 'frozen', False):
            path = os.path.dirname(sys.executable)
        else:
            path = os.path.dirname(os.path.realpath(__file__))
        return os.path.join(path, resource_path)
        # Get the base path to the extracted files
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, resource_path)