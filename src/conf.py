MODULES: list[str] = [
    "selenium",
    "WebAutomation.dolphin_anty"
]

# ENTITIES = [
#     "WebAutomation.dolphin_anty.script.AntyDolphinScript",
#     "WebAutomation.for_selenium.driver.script.By",
#     "WebAutomation.for_selenium.driver.script.FindOptions",
#     "WebAutomation.for_selenium.driver.script.FindOptions"
# ]

# ENTITIES_FLAG = True

EXCLUDED_ENTITIES: list[str] = [
    "selenium.webdriver.common.devtools.*",
    "WebAutomation.dolphin_anty.program.*"
    # "WebAutomation.dolphin_anty.conf.AUTH_TOKEN"
]

PORT: int = 8000