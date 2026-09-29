export interface StoredFile {
  key: string;
  url: string;
}

export interface StorageDriver {
  put(key: string, data: Buffer, contentType: string): Promise<StoredFile>;
  delete(key: string): Promise<void>;
}
