import argparse
from pathlib import Path

from . import auth
from .db import connect


def main():
    parser = argparse.ArgumentParser(description="Mantenimiento de Pastillas")
    parser.add_argument("command", choices=["backup", "reset-password"])
    parser.add_argument("value", help="Destino de la copia o nombre del usuario")
    args = parser.parse_args()
    with connect() as db:
        if args.command == "backup":
            target = Path(args.value)
            if target.exists():
                parser.error("El archivo de destino ya existe.")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch(mode=0o600, exist_ok=False)
            with connect(str(target)) as backup:
                db.backup(backup)
            print("Copia SQLite consistente creada.")
        else:
            import getpass
            password = getpass.getpass("Nueva contraseña (12–256 caracteres): ")
            auth.credentials(dict(username=args.value, password=password))
            changed = db.execute("UPDATE users SET password=? WHERE username=?", (auth.hash_password(password), args.value)).rowcount
            if not changed:
                parser.error("El usuario no existe.")
            db.execute("DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE username=?)", (args.value,))
            db.commit()
            print("Contraseña actualizada; sesiones revocadas.")


if __name__ == "__main__":
    main()
