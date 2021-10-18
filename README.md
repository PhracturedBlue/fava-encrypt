# Encrypted Fava
This Dockerfile provides a solution for keeping Fava online while keeping beancount data encrypted at rest.
The basic concept is to encrypt your beancount files using `securefs`, and to decrypt these only for a short
duration when Fava needs to read them.  The user's password is (indirectly) used to decrypt the files such that
the securefs password is never stored.  The process is wrapped with nginx to provide authentication and to
launch the encryption on demand.

## Limitations
Although the password is never stored, the beancount files will be available in a decrypted state for a short time
after the user accesses a beancount page.  These are only visible inside the Docker container, and not on the
host, but still available.  This image is not meant to be used on untrusted servers, but instead to keep financial
data secure at-rest (i.e. most of the time when beancount is not being used).

## Installing

### Pre-Requisities
  * Beancount directory that has been previously encrypted with SecureFS
  * `database.beancount` file at the root-level of the SecureFS mount
    * Using a different beancount filename just requires some minor changes to the docker-compose.yml file

### Steps
  * Mount SecureFS data somewhere (referred to as $SECUREFS_PATH below)
    * The following assumes that the top-level beancount file is in $SECUREFS_PATH/database.beancount
  * Create a file `$SECUREFS_PATH/.encrypted` (at the same level as the beancount file)
    * This is used by Fava to detect if the path is currently decrypted or not
  * Copy the `plugins/enable_encryption.py` file to `$SECUREFS_PATH/plugins/enable_encryption.py`
  * Add `plugin "plugins.enable_encryption" ""` to the database.beancount file (near tehe top)
  * Unmount SecureFS
  * Generate `auth.token` file from securefs/browser-passwords
    ```
    pip install -m venv .venv
    .venv/bin/pip install cryptography
    .venv/bin/python listener.py --set_password
      <enter SecureFS password>
      <enter browser password>
    ```
  * Update `docker-compose.yml` file with appropriate SecureFS path
  * If this docker container will sit behind a reverse-proxy, set `NGINX_PORT_REDIRECT` to `off`
    in `docker_compose.yml`.  This controls whether nginx redirects contain the port # or not.
    Normally they are needed if the browser connects directly to the image, and not if the browser
    connects to the image via a reverse-proxy
  * Build image: `docker-compose build`
  * Run image: `docker-compose up`
  
## How it works
 * Nginx receives all connections
 * Each request is forwarded to the `listener` to check for authentication
   * Fava `change` queries are not authenticated and do not trigger decryption
 * listener checks if user has a valid `auth` token < 24hours old
   * if no, then nginx sends user to login page
     * User enters password, which is validated, hashed and returned as an `auth` cookie
   * if yes, then listenr checks if path is decrypted yet.
     * If not, user's token is used as the key to decrypt the securefs password which is
       then used to temporarily decrypt the beancount sub-directory.
     * If the path is already decrypted, the timer is reset for when the path will be unmounted
 * If authentication was successful and the path is now decrypted, nginx forwards the request to fava
 * The beancount plugin monkey-patches fava's change-detection code to ignore `change` requests when
   the beancount subdir is not decrypted
   * Fava sends a `change` query every 3 seconds, so we need to ignore these to prevent them keeping
     the path decrypted indefinitely.  However, if Fava sees the path change from decrypted to encryted,
     it would typically trigger a refresh which would then cause decryption to happen as soon as it ended.
     The patch only allows Fava to notice file-changes if the path is alredy decrypted

## Managing Passwords
There are two different passwords used: 1) the SecureFS password, needed to decrypt the beancount files, and
2) the User's password that is entered in the browser.  The authentication 1st hashes the user's
browser-password, encrypts it (via Fernet symmetric encryption) with a private-key, and returns it as a cookie
token to the browser.  This token is only valid for 24 hours (a built-in capability of Fernet tokens...
overriding the token-age at the browser will not bypass this).

The user's hashed password (but not the password itself) can be recovered from the `auth` token using the
private-key.  This hashed password is then used as a key to decrypt the SecureFS password.

This process allows having  changeable auser-defined password for browser-entry and a independent password for
SecureFS accessr, while limiting the exposure of the browser's access to 24 hours between password entry.

# Beancount and GPG   
Beancount has native support for GPG encryption at the file level, and Fava can support that as well, seemingly
making this project a waste of time.  However teh GPG process does not work very well with multi-file beancount
files (in my experience) and using it disables editing in Fava.  Additionally, using Fava-encrypt allows keeping
other documents (like account statements) encrypted at rest while still being available to Fava as needed.
functionality in Fava.
