from harness.memory import ConversationSession, MemoryManager


def test_conversation_session():
    session = ConversationSession(channel_id=1001, max_turns=3)
    session.set_system_prompt("You are a helpful assistant.")

    messages = session.get_messages()
    assert len(messages) == 1
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are a helpful assistant."

    session.add_user_message("Hello", author_name="Alice")
    messages = session.get_messages()
    assert len(messages) == 2
    assert messages[1]["role"] == "user"
    assert "[Alice]: Hello" in messages[1]["content"]

    session.add_assistant_message("Hi Alice!")
    messages = session.get_messages()
    assert len(messages) == 3
    assert messages[2]["role"] == "assistant"
    assert messages[2]["content"] == "Hi Alice!"

    session.clear()
    cleared = session.get_messages()
    # System prompt retained on clear
    assert len(cleared) == 1
    assert cleared[0]["role"] == "system"


def test_conversation_session_with_user_info():
    session = ConversationSession(channel_id=1002)
    user_info = {
        "username": "forbf",
        "display_name": "Forb",
        "bio": "Lead developer, loves Python",
        "roles": ["Admin", "Developer"],
        "server": "Dev Lounge",
        "channel": "bot-test",
    }
    session.add_user_message("Write a script", user_info=user_info)
    msgs = session.get_messages()
    assert len(msgs) == 1
    content = msgs[0]["content"]
    assert "User: Forb (@forbf)" in content
    assert "About User: Lead developer, loves Python" in content
    assert "Roles: Admin, Developer" in content
    assert "Server: Dev Lounge" in content
    assert "Channel: #bot-test" in content
    assert "Write a script" in content


def test_conversation_session_with_mentioned_users():
    session = ConversationSession(channel_id=1003)
    user_info = {
        "username": "forbf",
        "display_name": "Forb",
        "server": "Dev Lounge",
        "channel": "general",
        "mentioned_users": [
            {
                "id": 9991,
                "username": "conley",
                "display_name": "Conley",
                "roles": ["Moderator", "Staff"],
                "joined_at": "2024-03-15",
                "created_at": "2021-08-01",
                "bio": "Frontend designer and gamer",
                "is_bot": False,
            }
        ],
    }
    session.add_user_message("who is this person @Conley", user_info=user_info)
    msgs = session.get_messages()
    assert len(msgs) == 1
    content = msgs[0]["content"]
    assert "Tagged User: Conley (@conley)" in content
    assert "Roles: Moderator, Staff" in content
    assert "Joined Server: 2024-03-15" in content
    assert "Bio/Info: Frontend designer and gamer" in content
    assert "who is this person @Conley" in content


def test_memory_manager():
    manager = MemoryManager(max_turns=5)
    s1 = manager.get_session(101)
    s2 = manager.get_session(102)
    assert s1 != s2
    assert s1.channel_id == 101
    assert s2.channel_id == 102

    s1.add_user_message("Msg1")
    assert len(s1.get_messages()) == 1
    assert len(s2.get_messages()) == 0

    manager.clear_session(101)
    assert len(s1.get_messages()) == 0
