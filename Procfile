fava: su -c "python3 fava_wrap.py --host 0.0.0.0 --port 5001 LEDGER_DIR/database.beancount" fava
auth: su -c "python3 listener.py --enc ENCRYPTED_DIR --dec /ledger --check_file LEDGER_DIR/.encrypted --keep_open KEEP_OPEN" fava
nginx: nginx -g 'daemon off;'

