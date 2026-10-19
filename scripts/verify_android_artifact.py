"""Verifica la alineación de 16 KB de las bibliotecas nativas de APK y AAB."""
import struct
import sys
import zipfile
import io


def verify(path):
    count = 0
    def libraries(archive, prefix=''):
        for name in archive.namelist():
            assert not name.endswith(('.sqlite', '.jks', '.keystore')), 'El paquete no debe contener datos ni firmas privadas'
            if name.endswith(('.imy', '.zip')):
                packed=archive.read(name)
                if packed.startswith(b'PK'):
                    with zipfile.ZipFile(io.BytesIO(packed)) as nested:
                        yield from libraries(nested,prefix+name+'/')
            if not name.endswith('.so'):
                continue
            yield prefix+name, archive.read(name)
    with zipfile.ZipFile(path) as archive:
        for name, data in libraries(archive):
            assert data[:5] == b'\x7fELF\x02', 'Se esperaba una biblioteca ELF de 64 bits: ' + name
            order = '<' if data[5] == 1 else '>'
            offset = struct.unpack_from(order+'Q', data, 32)[0]
            size, entries = struct.unpack_from(order+'HH', data, 54)
            for index in range(entries):
                entry = offset + index * size
                kind = struct.unpack_from(order+'I', data, entry)[0]
                if kind == 1:
                    alignment = struct.unpack_from(order+'Q', data, entry+48)[0]
                    assert alignment >= 16384, f'{name}: PT_LOAD debe admitir páginas de 16 KB, alineación={alignment}'
            count += 1
    assert count, 'No se encontraron las bibliotecas del intérprete'
    print(f'{path}: {count} bibliotecas de 64 bits compatibles con páginas de 16 KB')


if __name__ == '__main__':
    for argument in sys.argv[1:]:
        verify(argument)
