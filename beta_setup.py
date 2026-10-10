import app

def main():
    app.initialise_database()
    store=app.beta_store()
    owner=store.owner()
    if owner:
        print(f"Owner already configured: {owner['email']}")
        answer=input('Reset the owner invite code? [y/N]: ').strip().lower()
        if answer in {'y','yes'}:
            print('\nNew owner invite code:', store.reset_invite(owner['user_id']))
            print('Copy it somewhere safe. The old code no longer works.')
        return
    email=input('Owner email: ').strip()
    owner,code=store.ensure_owner(email)
    print('\nOwner account created.')
    print('Email:',owner['email'])
    print('Invite code:',code)
    print('\nCopy this code somewhere safe. It is stored only as a one-way hash.')
if __name__=='__main__': main()
