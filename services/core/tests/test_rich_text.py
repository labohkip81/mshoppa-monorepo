# ruff: noqa: F811
import pytest
from rest_framework.exceptions import ValidationError

from apps.rich_text import RichTextField, clean_rich_text, plain_text
from tests.test_foundation import (  # noqa: F401
    application,
    business,
    client,
    login,
    mutate,
    owner,
    reset_throttles,
    staff,
)


def test_formatting_retained_and_unsafe_content_removed():
    result = clean_rich_text('<h2 onclick="evil()">Returns</h2><p><strong>30 days</strong> &amp; original packaging.</p><ul><li>Receipt</li></ul><script>evil()</script><img src=x onerror=evil()><a href="javascript:evil()">unsafe</a><a href="https://example.com" style="color:red">link</a>')
    assert '<h2>Returns</h2>' in result and '<strong>30 days</strong>' in result and '<ul><li>Receipt</li></ul>' in result
    assert 'evil' not in result and '<img' not in result and 'style=' not in result
    assert 'href="https://example.com"' in result and 'noopener noreferrer' in result


def test_limits_count_text_and_preserve_plain_text():
    field = RichTextField(5, allow_blank=True)
    assert field.run_validation('<strong>Hello</strong>') == '<strong>Hello</strong>'
    with pytest.raises(ValidationError):
        field.run_validation('<p>Longer</p>')
    assert clean_rich_text('A & B\n2 < 3') == 'A & B\n2 < 3'
    assert clean_rich_text('<p><br></p>') == ''
    assert plain_text(clean_rich_text('<script>evil()</script>A & B')) == 'A & B'
    with pytest.raises(ValidationError):
        field.run_validation('<p>' + 'a'*5000 + '</p>')


@pytest.mark.django_db
def test_settings_and_product_html_round_trip(client, owner, business):
    login(client, owner)
    url=f'/api/businesses/{business.pk}/settings/'
    html='<h2>Our policy</h2><p><strong>Returns</strong> within 30 days.</p><ol><li>Contact us</li></ol>'
    fields=['terms_conditions','privacy_policy','return_refund_policy']
    response=mutate(client,url,{**dict.fromkeys(fields,html),'description':'<p>A <em>lovely</em> shop.</p>'},'patch')
    assert response.status_code==200,response.data
    saved=client.get(url).json()
    for field in fields:
        assert saved[field]==html
    product=mutate(client,f'/api/businesses/{business.pk}/products/',{'name':'Rich product','description':html+'<script>evil()</script>','price':'10','stock':1})
    assert product.status_code==201,product.data
    assert product.json()['description']==html
    business.store_settings.refresh_from_db()
    assert business.store_settings.terms_conditions==html
