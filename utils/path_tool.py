import os



def get_project_root():
    current_path = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_path)
    project_root = os.path.dirname(current_dir)
    return project_root




def get_abs_path(relative_path):
    project_root = get_project_root()
    return os.path.join(project_root, relative_path)