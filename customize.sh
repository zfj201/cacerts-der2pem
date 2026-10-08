SKIPUNZIP=0
[ "$API" -ge 26 ] || abort 'Android 8 (API 26) or newer is required'
[ -x /system/bin/app_process ] || abort 'app_process is required'
set_perm_recursive "$MODPATH" 0 0 0755 0644
set_perm "$MODPATH/service.sh" 0 0 0755
set_perm "$MODPATH/verify.sh" 0 0 0755
ui_print 'Validates and normalizes existing writable tmpfs certificate directory mounts.'
ui_print 'Requires a CA injection provider such as AlwaysTrustUserCerts.'
ui_print 'This module does not install a CA or replace that provider.'
