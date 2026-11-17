"""Pure slot selection: forced, online favorites, then category rotation."""
def select_sources(config,live_sources,scout_limit,rotation=0,retained=()):
    if not config.get('running'):return []
    if type(scout_limit) is not int or type(config.get('slots')) is not int:return []
    capacity=max(0,min(40,scout_limit,config['slots']))
    by_identity={}
    for source in live_sources:
        if source.get('live') is True and source.get('platform') in ('twitch','kick') and isinstance(source.get('login'),str):
            identity=(source['platform'],source['login'].lower())
            by_identity.setdefault(identity,source)
    chosen=[];seen=set()
    def add(identity):
        if identity in by_identity and identity not in seen and len(chosen)<capacity and sum(v['platform']==identity[0] for v in chosen)<config.get('platformSlots',{}).get(identity[0],capacity):
            seen.add(identity);chosen.append(by_identity[identity])
    for entry in config.get('forced',[]):add((entry['platform'],entry['login'].lower()))
    ranked=sorted(by_identity,key=lambda identity:(-by_identity[identity].get('viewers',0),identity))
    for category in config.get('forcedCategories',[]):
        for identity in list(retained)+ranked:
            if identity in by_identity and identity not in seen and identity[0]==category['platform'] and by_identity[identity].get('categoryId')==category['id']:
                add(identity);break
    for entry in config.get('favorites',[]):add((entry['platform'],entry['login'].lower()))
    categories={(c['platform'],c['id']) for c in config.get('categories',[])}
    # Keep automatic scouts stable only after explicit priorities claim their slots.
    for identity in retained:
        if identity in by_identity and (not categories or (identity[0],by_identity[identity].get('categoryId')) in categories):add(identity)
    pool=[identity for identity in ranked if identity not in seen and (not categories or (identity[0],by_identity[identity].get('categoryId')) in categories)]
    if pool:
        offset=rotation%len(pool)
        for identity in pool[offset:]+pool[:offset]:add(identity)
    return chosen
