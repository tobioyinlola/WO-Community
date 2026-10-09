import factory

from apps.accounts.models import User, UserRole, UserStatus


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"member{n}@example.com")
    status = UserStatus.ACTIVE
    password = factory.django.Password("a-long-test-passphrase")


class UserRoleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserRole

    user = factory.SubFactory(UserFactory)
    role = "member"
