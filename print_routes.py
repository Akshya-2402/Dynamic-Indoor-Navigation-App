from app import app
rules = sorted([(r.rule, sorted(r.methods)) for r in app.url_map.iter_rules()], key=lambda x: x[0])
for rule, methods in rules:
    print(rule, methods)
