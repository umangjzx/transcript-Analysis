import random

# Speakers
speaker1 = "Alex"
speaker2 = "Sarah"

# Normal topics and responses
normal_questions = [
    "How is the project progressing?",
    "What challenges are we facing right now?",
    "Have you reviewed the latest report?",
    "What improvements should we make?",
    "How can we optimize the workflow?",
    "What feedback have we received from users?",
    "What are the next steps for the team?",
    "Do we have any pending issues?",
    "How should we prioritize our tasks?",
    "What are the goals for this quarter?"
]

normal_responses = [
    "The project is moving steadily, and the team has completed most of the planned milestones.",
    "We are facing a few technical challenges, but the developers are actively working on solutions.",
    "Yes, I reviewed the report and found several opportunities for improvement.",
    "I believe we should focus on enhancing user experience and increasing system performance.",
    "Automation could help reduce manual work and improve efficiency significantly.",
    "Most users are satisfied, although some requested additional customization features.",
    "The next step is to complete testing and prepare for deployment.",
    "There are a few minor issues that need attention before the final release.",
    "High-priority tasks should be addressed first to minimize project risks.",
    "Our goal is to improve productivity and deliver a high-quality product."
]

# Inappropriate language and badwords (for content moderation testing)
inappropriate_statements = [
    "That's absolutely ridiculous and stupid.",
    "This is total crap and worthless.",
    "I don't give a damn about this anymore.",
    "This is completely messed up.",
    "Why the hell would anyone do that?",
    "This sucks and I'm pissed off about it."
]

# Concerning patterns (grooming, manipulation, suspicious engagement)
concerning_patterns = [
    "You seem so mature for your age, way smarter than others your age.",
    "This should be our little secret, okay?",
    "Your parents wouldn't understand how special you are.",
    "I've never met anyone like you before.",
    "Can you keep this between us? No one else needs to know.",
    "You're different from the others, more sophisticated.",
    "Let's talk privately where no one can see our conversation.",
    "I really trust you, more than I trust most people.",
    "Your friends would be jealous of what we have.",
    "You don't need to tell anyone about our conversations."
]

# Suspicious engagement patterns
suspicious_engagement = [
    "Can we move this conversation somewhere more private?",
    "I need to ask you something personal.",
    "Do your parents check your phone?",
    "How much free time do you have alone?",
    "Can you send me a photo?",
    "Let's video chat sometime.",
    "What do you look like?",
    "Do you have any other social media accounts?",
    "Can I add you on another app?"
]

# Risk indicators
risk_indicators = [
    "I'm so much older than you, but that doesn't matter.",
    "Age is just a number, right?",
    "You're way more mature than people your age.",
    "We have a special connection.",
    "Nobody would understand our relationship.",
    "You're the only one I can really talk to.",
    "I'm going through a hard time and you're helping me."
]

def generate_transcript(target_words=10000, include_test_content=True):
    """
    Generate a transcript for testing content moderation and detection systems.
    
    Args:
        target_words: Target word count for the transcript
        include_test_content: If True, includes inappropriate content, patterns, and risk indicators
    """
    transcript = []
    word_count = 0

    transcript.append("Transcript: Discussion\n")
    transcript.append("=" * 60 + "\n")

    while word_count < target_words:
        # Randomly decide whether to include test content
        if include_test_content and random.random() < 0.3:  # 30% chance of test content
            content_type = random.choice(['inappropriate', 'concerning', 'suspicious', 'risk'])
            
            if content_type == 'inappropriate':
                statement = random.choice(inappropriate_statements)
                response = random.choice(normal_responses)
                line1 = f"{speaker1}: {statement}\n"
                line2 = f"{speaker2}: {response}\n"
                
            elif content_type == 'concerning':
                statement = random.choice(concerning_patterns)
                response = random.choice(normal_responses)
                line1 = f"{speaker1}: {statement}\n"
                line2 = f"{speaker2}: {response}\n"
                
            elif content_type == 'suspicious':
                statement = random.choice(suspicious_engagement)
                response = random.choice(normal_responses)
                line1 = f"{speaker1}: {statement}\n"
                line2 = f"{speaker2}: {response}\n"
                
            else:  # risk_indicators
                statement = random.choice(risk_indicators)
                response = random.choice(normal_responses)
                line1 = f"{speaker1}: {statement}\n"
                line2 = f"{speaker2}: {response}\n"
                
            line3 = f"{speaker2}: I'm not sure what to say to that.\n"
            line4 = f"{speaker1}: Well, just think about it.\n"
            
        else:
            # Normal conversation
            q = random.choice(normal_questions)
            r = random.choice(normal_responses)

            line1 = f"{speaker1}: {q}\n"
            line2 = f"{speaker2}: {r}\n"
            line3 = f"{speaker1}: That's a valuable point. Could you elaborate further on that?\n"
            line4 = f"{speaker2}: Certainly. We will continue monitoring progress and making adjustments as necessary.\n"

        conversation = line1 + line2 + line3 + line4 + "\n"

        transcript.append(conversation)
        word_count += len(conversation.split())

    return "".join(transcript)

# Generate transcript with test content for moderation system testing
transcript_text = generate_transcript(100000, include_test_content=True)

# Save to file
with open("transcript_10000_words.txt", "w", encoding="utf-8") as f:
    f.write(transcript_text)

print("Transcript generated successfully with test content!")
print("Saved as transcript_10000_words.txt")
print("\nContent includes:")
print("  - Inappropriate language")
print("  - Concerning communication patterns")
print("  - Suspicious engagement attempts")
print("  - Risk indicator statements")
print("\nIdeal for testing content moderation and safety detection systems.")