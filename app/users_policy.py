from flask_login import current_user

class UsersPolicy:
    def __init__(self, user=None):
        self.user = user

    def create(self):
        return current_user.is_admin()

    def delete(self):
        return current_user.is_admin()

    def edit(self):
        return current_user.is_admin() or current_user.is_moderator()

    def find(self):
        return self.user.id == int(current_user.id)

    def review(self):
        return self.user.id == int(current_user.id) or current_user.is_moderator()