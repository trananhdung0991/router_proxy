
from router.proxy import ProxyManager
from router.db.db_init import DBInit

db_init = DBInit()
proxy = ProxyManager(db_init)

