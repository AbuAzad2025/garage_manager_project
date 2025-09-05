from wtforms.validators import ValidationError
from sqlalchemy import func

class Unique:
    def __init__(self, model, field, message=None, case_insensitive=False, normalizer=None):
        self.model = model
        self.field = field
        self.message = message or "Value already exists."
        self.case_insensitive = case_insensitive
        self.normalizer = normalizer

    def __call__(self, form, field):
        data = field.data
        if self.normalizer:
            data = self.normalizer(data)
        if not data:
            return

        query = self.model.query
        column = getattr(self.model, self.field)

        if self.case_insensitive and isinstance(data, str):
            query = query.filter(func.lower(column) == data.lower())
        else:
            query = query.filter(column == data)

        # لو تعديل (id موجود) → تجاهل نفسه
        if getattr(form, "id", None) and form.id.data:
            query = query.filter(self.model.id != form.id.data)

        if query.first():
            raise ValidationError(self.message)
