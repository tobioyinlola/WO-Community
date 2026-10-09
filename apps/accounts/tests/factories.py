import factory

from apps.accounts.models import User, UserRole, UserStatus


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"member{n}@example.com")
    status = UserStatus.ACTIVE
    password = factory.PostGenerationMethodCall("set_password", "a-long-test-passphrase")


class UserRoleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserRole

    user = factory.SubFactory(UserFactory)
    role = "member"
