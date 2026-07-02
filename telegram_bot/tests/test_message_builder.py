from telegram_bot.message_builder import build_order_message, build_customer_list, build_session_summary, escape_html


def test_escape_html_replaces_special_chars():
    assert escape_html('<a&b>') == '&lt;a&amp;b&gt;'


def test_build_order_message_default_template():
    output = build_order_message(
        commenter='John Doe',
        comment='Item <1> & size',
        profile_url='https://t.me/john',
        collected_at='2026-06-25 15:00',
        comment_id='123',
    )

    assert 'John Doe' in output
    assert '&lt;1&gt;' in output
    assert '<b>Name:</b>' in output
    assert '<b>Profile:</b>' not in output
    assert '3:00 PM' in output


def test_build_order_message_custom_template_mustache():
    template = 'Hello {{commenter}}, order: {{comment}} at {{collected_at}}'
    output = build_order_message(
        commenter='Ann',
        comment='2 pcs',
        profile_url=None,
        collected_at='2026-06-25 16:00',
        comment_id='ABC',
        template=template,
    )
    assert 'Hello Ann, order: 2 pcs at 2026-06-25 16:00' == output


def test_build_customer_list_empty():
    result = build_customer_list([])
    assert 'No customers yet' in result


def test_build_customer_list_sorted_by_order_count():
    customers = [
        {'name': 'Jane', 'order_count': 1},
        {'name': 'Bob', 'order_count': 3},
    ]
    result = build_customer_list(customers)
    assert result.index('Bob') < result.index('Jane')


def test_build_session_summary_default_template():
    output = build_session_summary(
        session_name='Live Session',
        order_count=5,
        customer_count=2,
        start_time='2026-06-25 14:00',
    )
    assert '<b>Live Session</b>' in output
    assert 'Orders:' in output
    assert 'Customers:' in output
