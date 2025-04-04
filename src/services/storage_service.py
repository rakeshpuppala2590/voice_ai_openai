from core.storage import Storage

class StorageService:
    def __init__(self):
        self.storage = Storage()

    def upload_file(self, file_path: str, destination: str):
        return self.storage.upload(file_path, destination)

    def download_file(self, file_name: str, destination: str):
        return self.storage.download(file_name, destination)

    def list_files(self, prefix: str = ''):
        return self.storage.list_files(prefix)

    def delete_file(self, file_name: str):
        return self.storage.delete(file_name)