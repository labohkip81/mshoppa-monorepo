from html import escape

from django.db import migrations


def preserve_plain_text(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    for product in Product.objects.all().iterator():
        if "<" in product.description or ">" in product.description:
            product.description = "<p>" + escape(product.description).replace("\n", "<br>") + "</p>"
            product.save(update_fields=["description"])


class Migration(migrations.Migration):
    dependencies = [("catalog", "0003_alter_variant_options_product_has_variants_and_more")]
    operations = [migrations.RunPython(preserve_plain_text, migrations.RunPython.noop)]
