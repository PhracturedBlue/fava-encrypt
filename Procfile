fava: su -c "fava --host 0.0.0.0 --port 5001 LEDGER_DIR/database.beancount" fava
auth: su -c "python3 listener.py --enc ENCRYPTED_DIR --dec /ledger --check_file LEDGER_DIR/.encrypted" fava
nginx: nginx -g 'daemon off;'

