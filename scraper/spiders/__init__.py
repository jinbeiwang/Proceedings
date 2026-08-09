"""会议 spider 包。新增会议在此注册到 SPIDERS 映射。"""
from .pharmasug import PharmaSUGSpider
from .phuse import PHUSESpider
from .sasgf import SASGlobalForumSpider
from .rpharma import RPharmaSpider
from .wayback_pharmasug import WaybackPharmaSUGSpider
from .pharmasug_cn import PharmaSUGChinaSpider

# 会议代码 -> spider 类。main.py 据此调度。
SPIDERS = {
    "pharmasug-us": PharmaSUGSpider,
    "pharmasug-cn": PharmaSUGChinaSpider,
    "pharmasug-wayback": WaybackPharmaSUGSpider,
    "phuse-eu": PHUSESpider,
    "phuse-us": PHUSESpider,
    "phuse-apac": PHUSESpider,
    "phuse-css": PHUSESpider,
    "sgf": SASGlobalForumSpider,
    "sugi": SASGlobalForumSpider,
    "r-pharma": RPharmaSpider,
}
