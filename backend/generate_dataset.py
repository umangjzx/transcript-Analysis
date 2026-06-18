"""
Generate a large-scale grooming NLI dataset (~18,000 samples).

Creates diverse premise-hypothesis pairs with:
- Balanced labels (entailment:neutral:contradiction ≈ 40:25:35)
- Systematic sentence template variations to avoid overfitting
- Cross-category hard negatives
- Contextual diversity (different settings, relationships, platforms)

Usage: python generate_dataset.py
Output: data/grooming_nli_dataset.json
"""

import json
import random
import itertools
import os
from pathlib import Path

random.seed(42)
OUTPUT = Path(__file__).parent / "data" / "grooming_nli_dataset.json"

# All hypothesis labels (matching the detection pipeline categories)
HYPOTHESES = {
    "secrecy": "asking someone to keep a secret or hide something",
    "parent_monitoring": "asking if parents monitor messages",
    "trust_building": "building emotional trust with someone",
    "manipulation": "manipulating or pressuring someone",
    "meeting": "arranging an in-person meeting",
    "address": "asking for a home address or location",
    "video_call": "requesting a video call or photos",
    "school_info": "asking about school or grade",
    "routine": "asking about daily routine or when someone is alone",
    "explicit": "sexually explicit or inappropriate content",
    "relationship": "building a close or romantic relationship",
    "bad_language": "threatening, abusive, or offensive language",
    "isolation": "isolating someone from friends or family",
    "age_deception": "lying about age or minimizing age difference",
    "gifts": "offering gifts or money to gain trust",
    "threats": "threatening or blackmailing someone",
    "gaming": "using games to lure someone to private channels",
    "normalizing": "normalizing inappropriate behavior",
    "guilt": "using guilt or emotional manipulation",
    "contact_info": "asking for phone number, email, or social media",
    "safe": "a safe or normal conversation",
}

# --- TEMPLATE POOLS ---
# Each category has many premise templates. {var} placeholders get filled
# with random choices from variation pools to create diversity.

TEMPLATES = {
    "secrecy": [
        "Don't tell {authority} about {topic}, okay?",
        "This is just between us, {endearment}.",
        "Promise me you won't say anything to {authority}.",
        "If {authority} finds out, {consequence}.",
        "Nobody else needs to know about {topic}.",
        "Keep this our little secret.",
        "You can't tell anyone about what we {activity}.",
        "Shh, {authority} wouldn't understand {topic}.",
        "This stays between you and me, got it?",
        "Let's not mention {topic} to anyone else.",
        "If you tell {authority}, they'll {negative_outcome}.",
        "I trust you not to share {topic} with others.",
        "We need to keep {topic} private from everyone.",
        "Your {authority} would overreact if they knew.",
        "It's safer if nobody knows about us {activity}.",
        "Delete {evidence} so nobody sees it.",
        "Don't screenshot {topic}, it's private.",
        "Hide {evidence} from {authority}.",
        "Make sure to clear your {device} history after we chat.",
        "Use a different {platform} so {authority} can't see.",
        "I'll get in trouble if anyone finds out about {topic}.",
        "People won't understand our {relationship}, keep it quiet.",
        "Don't even tell your {friend} about this.",
        "Remember, {topic} is our special thing.",
        "Erase our messages after reading them.",
    ],
    "parent_monitoring": [
        "Do your parents check your {device}?",
        "Can {authority} see what we're talking about?",
        "Does your {authority} read your {messages}?",
        "Are your parents strict about your {device}?",
        "Do they have your {password}?",
        "Is there a way to chat without {authority} knowing?",
        "When do your parents go through your {device}?",
        "Do you have parental controls on your {device}?",
        "Can your {authority} access your {platform} account?",
        "Does anyone else use your {device}?",
        "Is your {platform} account linked to your parents?",
        "Do your parents know your {password}?",
        "Is your {device} in your room or a shared space?",
        "Do your parents monitor your screen time?",
        "Can they see your notifications?",
        "Does your school track your {device} usage?",
        "Are your {messages} end-to-end encrypted?",
        "Do your parents follow you on {platform}?",
        "Who has access to your email?",
        "Can {authority} see your search history?",
    ],
    "trust_building": [
        "You can tell me anything, I'll always be here for you.",
        "I feel like we have a special connection.",
        "You're {compliment} for your age.",
        "Nobody understands you like I do.",
        "I'm the only one who really cares about you.",
        "You can trust me with anything, {endearment}.",
        "We have something special that others won't get.",
        "I've never felt this way about anyone before.",
        "You're not like the other {kids}, you're {compliment}.",
        "I'll always protect you no matter what.",
        "You're the most {compliment} person I know.",
        "I feel like I can be myself around you.",
        "We're soulmates, don't you think?",
        "Nobody else makes me feel the way you do.",
        "I'll never judge you, unlike {authority}.",
        "You're safe with me, I promise.",
        "I understand you better than your {friend} do.",
        "We have a bond that nobody can break.",
        "I think about you all the time.",
        "You're the highlight of my {time_period}.",
    ],
    "manipulation": [
        "If you really {care} about me, you would do this.",
        "After everything I've done for you, you owe me.",
        "You're being so ungrateful right now.",
        "Nobody else will ever {care} about you like I do.",
        "I'll be so {emotion} if you say no.",
        "Fine, I guess you don't {care} about me then.",
        "I thought you were {compliment}, I guess I was wrong.",
        "If you don't {action}, I'll {consequence}.",
        "You're the only thing keeping me going.",
        "I might {self_harm} if you leave me.",
        "Everyone else has abandoned me, don't you do it too.",
        "You promised me. Are you a liar?",
        "I thought we were {relationship}. Was I wrong?",
        "You're acting just like your {authority}.",
        "I gave up everything for you and this is how you repay me?",
        "Maybe I should just {consequence} since you don't care.",
        "Don't you want to make me happy?",
        "I can't believe you'd do this to me after all we've been through.",
        "You're so selfish. I just wanted to {action}.",
        "If you {care} about us, prove it.",
    ],
    "meeting": [
        "Let's meet up at {location}, just the two of us.",
        "Can you sneak out {time}? I'll pick you up.",
        "Meet me at {location} after {activity}.",
        "Don't tell anyone you're coming to see me.",
        "I know a quiet place where nobody will see us.",
        "Come to my {place} when {authority} is at work.",
        "Let's hang out at {location} this {time}.",
        "I'll be waiting for you at {location}.",
        "Can you get away from {authority} for a few hours?",
        "I want to see you in person. Where should we meet?",
        "Sneak out tonight and I'll drive you.",
        "Let's meet somewhere private.",
        "Come over to my {place}, nobody will be home.",
        "I want to spend time alone with you.",
        "Let's find a place where it's just us.",
        "Skip {activity} and come see me instead.",
        "I'll rent a {place} so we can be alone.",
        "Meet me behind the {location}.",
        "Tell {authority} you're going to {excuse}.",
        "Let's go for a drive, just you and me.",
    ],
    "address": [
        "Where do you live? What's your address?",
        "Which {area} are you in?",
        "Is your house near {landmark}?",
        "I want to {reason} to your place.",
        "What street do you live on?",
        "How far is your house from {landmark}?",
        "Can you drop me a pin of your location?",
        "Send me your {location_type} on {platform}.",
        "I need your address to {reason}.",
        "Which apartment building is yours?",
        "What's the nearest cross-street to your house?",
        "Do you live in a house or apartment?",
        "What does your house look like from outside?",
        "What floor do you live on?",
        "Is there a back entrance to your building?",
        "Where exactly is your bedroom window?",
        "How do I get to your place from {landmark}?",
        "What's the address? I'll put it in my GPS.",
        "Are you near the {landmark}? I'm driving by.",
        "Text me your location so I can find you.",
    ],
    "video_call": [
        "Send me a {photo_type} of yourself.",
        "Let's video call {time}.",
        "Can you turn on your camera?",
        "I want to see you right now, send a {photo_type}.",
        "Take a selfie and send it to me.",
        "Show me what you look like {context}.",
        "Let's FaceTime when {authority} goes to sleep.",
        "Send me a {photo_type}, I miss your face.",
        "Can we do a video chat? I want to see you.",
        "Turn on your {device} camera for me.",
        "Film yourself doing {activity} and send it.",
        "I want to see what you're wearing, show me.",
        "Let me see your face, {endearment}.",
        "Take a picture in your {clothing} for me.",
        "Can you send a full body {photo_type}?",
        "Show me your {room} on camera.",
        "I'll send you one first if you send me one.",
        "Do you have a camera on your {device}?",
        "Record a video of yourself for me.",
        "I just want to see your {feature}, send a pic.",
    ],
    "school_info": [
        "What school do you go to?",
        "What grade are you in?",
        "What time does school finish?",
        "Do you walk home from school?",
        "What's the name of your school?",
        "Where is your school located?",
        "Which class are you in {time}?",
        "What time does your first class start?",
        "Are you in middle school or high school?",
        "How old are the other {kids} in your class?",
        "Does your school have {feature}?",
        "What's your teacher's name?",
        "Do you take the bus or get dropped off?",
        "What entrance do you use at school?",
        "When's your lunch break?",
        "Do you have any free periods?",
        "Which route do you take to school?",
        "Is your school near your house?",
        "When does summer break start for you?",
        "Are there cameras at your school?",
    ],
    "routine": [
        "What time are you usually home alone?",
        "When do your parents leave for work?",
        "Are you alone right now?",
        "When does {authority} get home?",
        "How long are you by yourself after school?",
        "What time do you go to bed?",
        "Does anyone else stay home with you?",
        "What's your daily schedule like?",
        "When is the house empty?",
        "Do you have time alone on {day}?",
        "What time does {authority} usually sleep?",
        "Are your parents home {time}?",
        "How often are you left alone?",
        "Is there a time when nobody's watching?",
        "When's the best time to call without anyone hearing?",
        "Does anyone check on you in the {time}?",
        "What time does everyone go to sleep at your house?",
        "When is your next day off from school?",
        "Are you home alone on weekends?",
        "When can we talk without {authority} around?",
    ],
    "explicit": [
        "Have you ever {explicit_action}?",
        "What are you wearing right now?",
        "I can teach you things about {explicit_topic}.",
        "Do you know what {explicit_topic} is?",
        "Have you done {explicit_action} before?",
        "I'll show you mine if you show me yours.",
        "Take off your {clothing} and send me a pic.",
        "Do you touch yourself?",
        "I want to {explicit_action} with you.",
        "Have you ever been with someone {older}?",
        "Let me see your body.",
        "Are you curious about {explicit_topic}?",
        "I'll teach you how to {explicit_action}.",
        "Do you know what happens between two people who {care}?",
        "Describe what you look like without {clothing}.",
        "I've been thinking about you in {context}.",
        "What would you do if I was there with you?",
        "You'd look {compliment} without clothes.",
        "I want to make you feel {emotion}.",
        "Have you ever watched {explicit_topic} videos?",
    ],
    "relationship": [
        "I think I'm falling in love with you.",
        "You're my {relationship} now, right?",
        "We belong together, {endearment}.",
        "Age is just a number between us.",
        "I want to be with you {time_period}.",
        "Do you feel the same way about me?",
        "We're meant to be together.",
        "You're the love of my life.",
        "I've never loved anyone like I love you.",
        "When you're {older}, we can be together publicly.",
        "Let's be exclusive. Don't talk to other {people}.",
        "You're mine and I'm yours.",
        "I dream about our future together.",
        "When can we make this official?",
        "I want to marry you someday.",
        "You make me feel things nobody else does.",
        "I wish I could hold you right now.",
        "Tell me you love me.",
        "Am I your favorite person?",
        "I get jealous when you talk to other {people}.",
    ],
    "bad_language": [
        "I'll hurt you if you don't do what I say.",
        "You're worthless, nobody will believe you.",
        "Shut up and do as you're told, you {insult}.",
        "I'll make your life miserable if you tell.",
        "You're nothing without me, {insult}.",
        "Nobody cares about you except me.",
        "You're stupid if you think anyone will help you.",
        "I'll destroy you if you leave.",
        "You deserve everything bad that happens to you.",
        "You're pathetic, you know that?",
        "Stop crying, you're being dramatic.",
        "You asked for this, don't pretend you didn't.",
        "If you were smarter, you'd just listen.",
        "You're a waste of space.",
        "I'll ruin your reputation.",
        "Nobody will ever want you.",
        "You think you're special? You're nothing.",
        "I should've never wasted my time on you.",
        "Keep talking and see what happens.",
        "You'll regret crossing me.",
    ],
    "isolation": [
        "Your {friend} aren't real friends. Only I care about you.",
        "Don't hang out with {name} anymore, they're a bad influence.",
        "You don't need anyone else when you have me.",
        "Those {people} are talking behind your back.",
        "Your {authority} doesn't understand you like I do.",
        "They'll just hurt you. Stay away from them.",
        "I'm the only person you can really trust.",
        "Stop spending time with {name}, they don't deserve you.",
        "Your family doesn't appreciate you.",
        "Everyone else will let you down eventually.",
        "You should distance yourself from {friend}.",
        "They're just using you. I'm different.",
        "You'd be happier if it was just us.",
        "Those {people} are toxic for you.",
        "Only talk to me from now on.",
        "Block {name} on {platform}, they're trouble.",
        "You don't need school friends, you have me.",
        "Your {authority} is trying to control you.",
        "Come to me when you're feeling lonely.",
        "We don't need anyone else in our lives.",
    ],
    "age_deception": [
        "I'm actually only {fake_age} too.",
        "Age doesn't matter when two people connect like us.",
        "I'm {fake_age}, just a few years older.",
        "Lots of {people} our age date.",
        "You're so {compliment}, nobody would guess your age.",
        "I look {young_descriptor} for my age.",
        "When I was your age, I dated someone {older}.",
        "Age is just a number, what matters is feelings.",
        "You're basically an adult already.",
        "In some places, {age} is old enough.",
        "Nobody needs to know the real age difference.",
        "You're more mature than most {adults}.",
        "I feel like we're the same age mentally.",
        "You act so grown up, I forget you're {age}.",
        "The age gap doesn't bother me if it doesn't bother you.",
        "By the time anyone notices, you'll be {legal_age}.",
        "My friends are all your age anyway.",
        "I relate to people your age more than mine.",
        "I promise I'm not that much older.",
        "Once you're {legal_age}, nobody can say anything.",
    ],
    "gifts": [
        "I'll buy you {gift} if you do something for me.",
        "Here's {money}, but don't tell {authority}.",
        "I got you a {gift}, open it when you're alone.",
        "Want me to buy you that {gift} you've been wanting?",
        "I'll pay for your {subscription} if you keep chatting with me.",
        "I'm sending you a {gift} in the mail.",
        "I can get you anything you want, just ask.",
        "Let me buy you {gift}, you deserve it.",
        "I'll give you {money} every time we {activity}.",
        "Do you need money? I can help.",
        "I put {money} in your {platform} account.",
        "I'll get you the new {gift} when it comes out.",
        "Want me to {reason}? I'll take care of it.",
        "I'll pay for your {activity}, don't worry.",
        "Accept this {gift} as a sign of how I feel.",
        "I'll send you a {gift} card. What store?",
        "I got you something special, but it's a secret.",
        "Tell me your wishlist and I'll buy it all.",
        "I want to spoil you, what do you need?",
        "I'm transferring {money} to your account now.",
    ],
    "threats": [
        "If you tell anyone, I'll {threat}.",
        "I have those {evidence} of you. Remember that.",
        "Tell anyone and I'll send those {evidence} to everyone.",
        "I know where you live. Keep your mouth shut.",
        "I'll hurt your {family} if you say anything.",
        "Nobody will believe you over me.",
        "Tell and I'll make sure you regret it.",
        "I'll destroy your life if you talk.",
        "Remember, I have {evidence}. Don't test me.",
        "If you leave, I'll show everyone what you did.",
        "I'll tell {authority} about {secret} unless you cooperate.",
        "You'll lose everything if people find out.",
        "I'll make sure nobody trusts you again.",
        "Tell and see what happens to your {family}.",
        "I'll get you expelled if you talk.",
        "Everyone will think you're {insult} if this comes out.",
        "You started this. You're just as guilty.",
        "I'll make it look like your fault.",
        "Cross me and you'll wish you hadn't.",
        "I have friends who can make your life difficult.",
    ],
    "gaming": [
        "Do you play {game}? Add me.",
        "Let's play together on a private server.",
        "What's your {platform} username?",
        "Join my Discord server, it's invite-only.",
        "Let's voice chat on {platform} while we play.",
        "I'll send you a friend request on {game}.",
        "We should play {game} late at night when it's quieter.",
        "I have a private {platform} group, want in?",
        "Let's move to {platform} where we can talk freely.",
        "Add me on {platform}, my DMs are open.",
        "I know a private chat room we can use.",
        "Let's play {game} on my private server.",
        "Download {platform}, nobody will find us there.",
        "I'll create a secret server just for us.",
        "Use this link to join my {platform} channel.",
        "Don't use your real name on {platform}.",
        "Let's switch to {platform} for better privacy.",
        "I'll gift you the game if you play with me.",
        "Come to my {platform} stream, I'll give you a shoutout.",
        "Let's do a 1-on-1 {game} session tonight.",
    ],
    "normalizing": [
        "Everyone does this at your age.",
        "This is totally normal between {people} who care.",
        "There's nothing wrong with what we're doing.",
        "All the other {kids} are doing it too.",
        "It's natural to feel this way.",
        "In other countries this is perfectly acceptable.",
        "Your {friend} probably do this too.",
        "I've done this with other {people}, it's fine.",
        "Society is too uptight about these things.",
        "This is how you learn about {topic}.",
        "It's educational, there's nothing bad about it.",
        "You're old enough to make your own choices.",
        "Don't be a baby, this is what grown-ups do.",
        "There's nothing to be scared of.",
        "It's just between friends, relax.",
        "This isn't a big deal, trust me.",
        "You'll thank me later for teaching you this.",
        "It's healthy and natural.",
        "Only immature people think this is wrong.",
        "You're overthinking it, just go with it.",
    ],
    "guilt": [
        "After everything I've done for you, this is how you treat me?",
        "I thought you cared about me. I guess I was wrong.",
        "You owe me after all I've sacrificed.",
        "I'm so {emotion} because of you.",
        "Maybe I should just disappear since you don't care.",
        "I can't believe you'd betray me like this.",
        "You're breaking my heart right now.",
        "I gave up everything for us.",
        "If you really {care} about me, you wouldn't do this.",
        "I'll be all alone if you leave.",
        "You promised me, are you a liar?",
        "I'm the only one who's ever been there for you.",
        "Think about how {emotion} I'll be if you say no.",
        "Don't you feel bad for making me feel this way?",
        "I'm crying because of what you said.",
        "Nobody else would put up with you like I do.",
        "I thought we were {relationship}.",
        "You're all I have left in this world.",
        "Without you, I have nothing to live for.",
        "I'll never forgive you if you leave now.",
    ],
    "contact_info": [
        "What's your {contact_type}? I'll {action} you.",
        "Give me your {platform} so we can talk there.",
        "Do you have {platform}? Add me.",
        "What's your number? I'll text you.",
        "Send me your {contact_type}.",
        "Add me on {platform}, my handle is...",
        "Let me have your email, I'll send you {thing}.",
        "What's your Snapchat? I want to send you {thing}.",
        "Do you have a private {platform} account?",
        "Here's my number, text me when {authority} isn't around.",
        "Create a new {platform} account just for us.",
        "Make a fake {platform} so nobody knows.",
        "What messaging app do you use?",
        "Let me add you on {platform}.",
        "Give me a way to reach you that's private.",
        "Use this number to text me, it's my burner.",
        "Do you have WhatsApp? It's more private.",
        "What's your personal email?",
        "Add my second account on {platform}.",
        "Download {platform} and message me there.",
    ],
    "safe": [
        "Good morning class, today we'll cover {subject}.",
        "Can you explain {subject} again please?",
        "The homework is due on {day}.",
        "Great job on the {assignment}, everyone.",
        "Remember to bring your {item} tomorrow.",
        "The field trip is scheduled for {day}.",
        "Please work in groups of {number}.",
        "Does anyone have questions about {subject}?",
        "The library is open until {time}.",
        "Don't forget to study for the {assignment}.",
        "Parent-teacher conferences are next {day}.",
        "The school play is at {time} in the auditorium.",
        "Please return your textbooks by {day}.",
        "The cafeteria is serving {food} today.",
        "Practice is cancelled due to {weather}.",
        "The science fair projects are due {day}.",
        "Please be respectful of others' opinions.",
        "Let's start with a review of last week's {subject}.",
        "The bus leaves at {time} sharp.",
        "Everyone did well on the {assignment}, keep it up.",
        "I'll post the grades online by {day}.",
        "See you all next {day}, have a good weekend.",
        "The new semester starts on {day}.",
        "Sign up for after-school clubs in the office.",
        "Your parents are welcome to attend the open house.",
    ],
}

# --- VARIABLE POOLS for template filling ---
VARS = {
    "authority": ["your mom", "your dad", "your parents", "your teacher",
                  "your family", "your guardian", "your brother", "your sister"],
    "topic": ["our conversations", "this", "what we do", "us talking",
              "our relationship", "what happened", "our chats"],
    "endearment": ["sweetie", "honey", "babe", "beautiful", "cutie",
                   "sweetheart", "love", "angel", "baby"],
    "consequence": ["they'll take your phone", "we can't talk anymore",
                    "I'll get in trouble", "bad things will happen",
                    "they'll separate us", "you'll be grounded"],
    "negative_outcome": ["take your phone away", "stop us from talking",
                         "ground you forever", "move you to a different school",
                         "blame you for this", "make you change schools"],
    "activity": ["do together", "talk about", "share", "did last time"],
    "evidence": ["our messages", "those photos", "the chat logs",
                 "our conversations", "the screenshots", "the videos"],
    "device": ["phone", "tablet", "laptop", "computer", "iPad"],
    "platform": ["Instagram", "Snapchat", "Discord", "TikTok", "WhatsApp",
                 "Telegram", "Signal", "Kik", "Twitter", "Facebook"],
    "messages": ["texts", "messages", "DMs", "chats"],
    "password": ["password", "passcode", "PIN", "lock code"],
    "compliment": ["mature", "smart", "special", "beautiful", "amazing",
                   "talented", "unique", "grown-up", "sophisticated", "perfect"],
    "kids": ["kids", "students", "girls", "boys", "teenagers", "people your age"],
    "time_period": ["day", "week", "life", "month"],
    "care": ["love", "care", "trust", "believe in"],
    "emotion": ["sad", "hurt", "devastated", "heartbroken", "depressed",
                "lonely", "miserable", "upset", "empty"],
    "action": ["do this", "help me", "send that", "come over", "stay"],
    "self_harm": ["hurt myself", "do something stupid", "disappear"],
    "relationship": ["special friends", "together", "a couple",
                     "more than friends", "soulmates", "in love"],
    "location": ["the park", "the mall", "my car", "behind the school",
                 "the parking lot", "the library", "the movies",
                 "the coffee shop", "my office", "the gym"],
    "time": ["tonight", "this weekend", "after school", "tomorrow night",
             "Saturday", "during lunch", "at midnight", "early morning"],
    "place": ["house", "apartment", "car", "room", "office"],
    "excuse": ["a friend's house", "the library", "the mall",
               "a sleepover", "study group", "tutoring"],
    "area": ["neighborhood", "part of town", "city", "suburb"],
    "landmark": ["the school", "the station", "the park", "the mall"],
    "location_type": ["address", "location", "coordinates"],
    "reason": ["send you something", "drop something off", "come visit",
               "surprise you", "pick you up", "drive by"],
    "photo_type": ["picture", "photo", "selfie", "pic", "snap"],
    "context": ["right now", "in that outfit", "when you wake up",
                "in your pajamas", "after you shower"],
    "clothing": ["shirt", "top", "outfit", "clothes", "jacket"],
    "room": ["room", "bedroom", "bathroom"],
    "feature": ["face", "smile", "eyes", "figure"],
    "subject": ["math", "science", "history", "English", "biology",
                "chemistry", "physics", "geography", "literature"],
    "day": ["Monday", "Tuesday", "Wednesday", "Friday", "next week"],
    "assignment": ["test", "quiz", "exam", "project", "essay"],
    "item": ["textbooks", "notebooks", "calculator", "lab coat"],
    "food": ["pizza", "tacos", "pasta", "sandwiches"],
    "weather": ["rain", "snow", "bad weather", "a storm"],
    "number": ["3", "4", "5", "2"],
    "friend": ["friends", "best friend", "buddies", "classmates"],
    "name": ["them", "that person", "your friend", "those people"],
    "people": ["people", "guys", "girls", "boys", "kids"],
    "insult": ["a liar", "worthless", "pathetic", "disgusting"],
    "family": ["family", "little sister", "little brother", "mom", "dad"],
    "secret": ["what you did", "our relationship", "your messages"],
    "game": ["Roblox", "Fortnite", "Minecraft", "Among Us", "GTA",
             "Valorant", "Apex", "Call of Duty"],
    "thing": ["something cool", "a surprise", "memes", "a gift"],
    "contact_type": ["number", "phone number", "email", "username"],
    "gift": ["a new phone", "AirPods", "a game console", "clothes",
             "shoes", "jewelry", "a laptop", "a gift card"],
    "money": ["$50", "$100", "$20", "some money", "cash"],
    "subscription": ["Netflix", "Spotify", "game pass", "phone plan"],
    "fake_age": ["16", "17", "15", "14", "18"],
    "young_descriptor": ["young", "youthful", "younger"],
    "older": ["older", "more experienced", "an adult"],
    "age": ["13", "14", "15", "16"],
    "legal_age": ["18", "16", "old enough"],
    "adults": ["adults my age", "people my age", "older people"],
    "explicit_action": ["kissed someone", "been intimate", "done stuff"],
    "explicit_topic": ["relationships", "intimacy", "adult things"],
    "threat": ["show everyone our messages", "tell your school",
               "hurt your family", "make you regret it",
               "ruin your life", "post your photos online"],
}

# --- Safe premises (used for contradiction against grooming hypotheses) ---
SAFE_PREMISES = [
    "The meeting is at 3pm in the main conference room.",
    "Please complete exercises 1-10 for homework.",
    "The school trip to the museum is next Friday.",
    "Your test results are really impressive, well done.",
    "Make sure to bring a packed lunch tomorrow.",
    "The library books are due back by the end of the week.",
    "Let's start today's lesson with chapter 4.",
    "Remember to get your permission slips signed.",
    "The basketball game is at 5pm, everyone's welcome.",
    "You can use the computer lab during free periods.",
    "The cafeteria menu is posted on the school website.",
    "Please hand in your essays by Monday morning.",
    "The fire drill will be sometime this week.",
    "After school tutoring is available in room 204.",
    "The school dance is on Saturday, tickets are $5.",
    "Remember to bring your gym clothes tomorrow.",
    "Parent-teacher meetings are scheduled for Thursday.",
    "The debate team practice is every Wednesday.",
    "The new school year calendar is online now.",
    "Let's review what we learned about fractions today.",
    "I'll be grading papers over the weekend.",
    "The choir concert is next Tuesday evening.",
    "Please return your library books before summer.",
    "The field day activities start at 9am sharp.",
    "Study groups can meet in the library after school.",
    "The yearbook committee needs more volunteers.",
    "Make sure your name is on your homework paper.",
    "Class starts in five minutes, please take your seats.",
    "The art supplies are in the cabinet by the window.",
    "We'll have a substitute teacher on Friday.",
    "The annual science fair is in three weeks.",
    "Please respect quiet hours in the library.",
    "The school store is open during lunch period.",
    "Remember to check the class blog for updates.",
    "The assembly is at 10am in the gymnasium.",
    "All projects must include a bibliography.",
    "The weather forecast says rain, bring an umbrella.",
    "Please don't run in the hallways.",
    "The next PTA meeting is on the first Tuesday.",
    "Your lab partners are posted on the board.",
]

PREFIXES = [
    "", "", "", "",  # mostly no prefix
    "Hey, ", "So, ", "Listen, ", "Look, ", "Okay so ", "Alright, ",
    "Um, ", "Hey listen, ", "You know, ", "By the way, ",
    "Real talk, ", "Between us, ", "Honestly, ", "Just saying, ",
]

SUFFIXES = [
    "", "", "", "", "",  # mostly no suffix
    " lol", " haha", " okay?", " right?", " yeah?",
    " please", " for real", " trust me", " I promise",
    " no cap", " fr", " seriously", " tbh",
]

TYPO_MAP = {
    "you": ["u", "you", "you"],
    "your": ["ur", "your", "your", "your"],
    "are": ["r", "are", "are"],
    "to": ["2", "to", "to"],
    "for": ["4", "for", "for"],
    "tonight": ["2night", "tonight", "tonight"],
    "because": ["cuz", "because", "bc"],
    "okay": ["ok", "okay", "k"],
    "please": ["pls", "please", "plz"],
    "people": ["ppl", "people", "people"],
    "want": ["wanna", "want", "want"],
    "going to": ["gonna", "going to", "going to"],
}


def fill_template(template: str) -> str:
    """Replace {var} placeholders with random choices from VARS pools,
    add optional prefix/suffix, and introduce occasional text-speak."""
    import re
    def replacer(match):
        key = match.group(1)
        if key in VARS:
            return random.choice(VARS[key])
        return match.group(0)
    result = re.sub(r"\{(\w+)\}", replacer, template)

    # Occasionally add texting-style variations (30% chance)
    if random.random() < 0.3:
        for word, replacements in TYPO_MAP.items():
            if word in result.lower() and random.random() < 0.25:
                result = result.replace(word, random.choice(replacements), 1)

    # Add prefix/suffix for diversity
    prefix = random.choice(PREFIXES)
    suffix = random.choice(SUFFIXES)
    if prefix and result[0].isupper():
        result = result[0].lower() + result[1:]
    return prefix + result + suffix


def generate_entailment_samples(target_per_category: int = 400) -> list:
    """Generate entailment (label=0) samples: premise matches hypothesis."""
    samples = []
    seen = set()
    for cat, templates in TEMPLATES.items():
        hypothesis = HYPOTHESES[cat]
        generated = 0
        attempts = 0
        while generated < target_per_category and attempts < target_per_category * 5:
            tmpl = random.choice(templates)
            premise = fill_template(tmpl)
            key = (premise, hypothesis)
            attempts += 1
            if key in seen:
                continue
            seen.add(key)
            samples.append({
                "premise": premise,
                "hypothesis": hypothesis,
                "label": 0
            })
            generated += 1
    return samples


def generate_contradiction_samples(target_per_category: int = 250) -> list:
    """Generate contradiction (label=2) samples: premise does NOT match hypothesis."""
    samples = []
    seen = set()
    categories = list(HYPOTHESES.keys())

    for cat in categories:
        hypothesis = HYPOTHESES[cat]
        generated = 0
        attempts = 0
        while generated < target_per_category and attempts < target_per_category * 5:
            # Strategy 1: safe premise vs grooming hypothesis (60%)
            # Strategy 2: cross-category premise vs wrong hypothesis (40%)
            if random.random() < 0.6 or cat == "safe":
                premise = random.choice(SAFE_PREMISES)
                # Add prefix/suffix for diversity on safe premises too
                prefix = random.choice(PREFIXES)
                suffix = random.choice(SUFFIXES)
                premise = prefix + premise + suffix
            else:
                other_cat = random.choice([c for c in categories if c != cat])
                tmpl = random.choice(TEMPLATES[other_cat])
                premise = fill_template(tmpl)
            key = (premise, hypothesis)
            attempts += 1
            if key in seen:
                continue
            seen.add(key)
            samples.append({
                "premise": premise,
                "hypothesis": hypothesis,
                "label": 2
            })
            generated += 1
    return samples


def generate_neutral_samples(target_per_category: int = 150) -> list:
    """Generate neutral (label=1) samples: premise is ambiguous/borderline."""
    samples = []
    seen = set()
    categories = list(HYPOTHESES.keys())

    # Neutral templates - phrases that COULD be concerning but are ambiguous
    neutral_premises = [
        "Do you have a ride home after practice?",
        "I'm proud of how much you've grown this year.",
        "You did amazing on that performance, really talented.",
        "Can I have your email to send the assignment details?",
        "We should set up a time to discuss your progress.",
        "You remind me of when I was your age.",
        "Don't share the exam answers with anyone.",
        "I worry about you walking home alone after dark.",
        "You're one of the most dedicated students I've had.",
        "Let me know if you need extra help after school.",
        "I brought snacks for the whole group today.",
        "Your parents should know about your great performance.",
        "I'll be in my office if anyone needs to talk.",
        "You seem upset today, is everything okay at home?",
        "Great work on the project, you're really talented.",
        "The team dinner is at my house on Saturday.",
        "I'll drive the group to the competition.",
        "You can call me if you ever need anything.",
        "I notice you've been quiet lately.",
        "Let's schedule a one-on-one meeting to review grades.",
        "You have real potential, I want to help you succeed.",
        "The whole team stays late on Thursdays for practice.",
        "I gave everyone a small award for their hard work.",
        "Does your family support your interest in this?",
        "You're welcome to use the equipment after hours.",
        "I'll be mentoring you this semester.",
        "Let's video call with the study group tonight.",
        "Can someone stay after to help organize?",
        "You should join the honors program.",
        "I noticed you've been spending less time with friends.",
    ]

    for cat in categories:
        hypothesis = HYPOTHESES[cat]
        generated = 0
        attempts = 0
        while generated < target_per_category and attempts < target_per_category * 5:
            premise = random.choice(neutral_premises)
            prefix = random.choice(PREFIXES)
            suffix = random.choice(SUFFIXES)
            premise_varied = prefix + premise + suffix
            key = (premise_varied, hypothesis)
            attempts += 1
            if key in seen:
                continue
            seen.add(key)
            samples.append({
                "premise": premise_varied,
                "hypothesis": hypothesis,
                "label": 1
            })
            generated += 1
    return samples


def generate_dataset(target_total: int = 18000) -> list:
    """
    Generate a balanced NLI dataset.
    Target distribution: ~40% entailment, ~25% neutral, ~35% contradiction.
    """
    n_categories = len(HYPOTHESES)

    # Calculate per-category targets
    entail_total = int(target_total * 0.40)
    neutral_total = int(target_total * 0.25)
    contra_total = int(target_total * 0.35)

    entail_per_cat = entail_total // n_categories
    neutral_per_cat = neutral_total // n_categories
    contra_per_cat = contra_total // n_categories

    print(f"Generating {target_total} samples across {n_categories} categories...")
    print(f"  Entailment: {entail_per_cat} × {n_categories} = ~{entail_per_cat * n_categories}")
    print(f"  Neutral:    {neutral_per_cat} × {n_categories} = ~{neutral_per_cat * n_categories}")
    print(f"  Contradiction: {contra_per_cat} × {n_categories} = ~{contra_per_cat * n_categories}")

    samples = []
    samples.extend(generate_entailment_samples(entail_per_cat))
    samples.extend(generate_neutral_samples(neutral_per_cat))
    samples.extend(generate_contradiction_samples(contra_per_cat))

    # Shuffle thoroughly
    random.shuffle(samples)

    # Report final distribution
    label_counts = {0: 0, 1: 0, 2: 0}
    for s in samples:
        label_counts[s["label"]] += 1

    print(f"\nFinal dataset: {len(samples)} samples")
    print(f"  Label 0 (entailment):    {label_counts[0]} ({label_counts[0]/len(samples)*100:.1f}%)")
    print(f"  Label 1 (neutral):       {label_counts[1]} ({label_counts[1]/len(samples)*100:.1f}%)")
    print(f"  Label 2 (contradiction): {label_counts[2]} ({label_counts[2]/len(samples)*100:.1f}%)")

    return samples


def verify_quality(samples: list):
    """Quick quality checks on the generated dataset."""
    # Check for exact duplicates
    seen = set()
    duplicates = 0
    for s in samples:
        key = (s["premise"], s["hypothesis"], s["label"])
        if key in seen:
            duplicates += 1
        seen.add(key)

    # Check premise length distribution
    lengths = [len(s["premise"]) for s in samples]
    avg_len = sum(lengths) / len(lengths)

    print(f"\nQuality check:")
    print(f"  Exact duplicates: {duplicates} ({duplicates/len(samples)*100:.1f}%)")
    print(f"  Avg premise length: {avg_len:.0f} chars")
    print(f"  Min/Max length: {min(lengths)}/{max(lengths)} chars")

    # Check hypothesis coverage
    hyp_counts = {}
    for s in samples:
        hyp_counts[s["hypothesis"]] = hyp_counts.get(s["hypothesis"], 0) + 1
    print(f"  Hypotheses covered: {len(hyp_counts)}/{len(HYPOTHESES)}")

    if duplicates > len(samples) * 0.05:
        print("  ⚠️  High duplicate rate - consider more template diversity")
    else:
        print("  ✓ Duplicate rate acceptable")


if __name__ == "__main__":
    samples = generate_dataset(target_total=18000)
    verify_quality(samples)

    os.makedirs(OUTPUT.parent, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(samples, f, indent=None, ensure_ascii=False)

    file_size_mb = os.path.getsize(OUTPUT) / (1024 * 1024)
    print(f"\nSaved to: {OUTPUT}")
    print(f"File size: {file_size_mb:.1f} MB")
    print(f"\nReady for fine-tuning:")
    print(f"  python finetune_model.py --epochs 5 --lr 3e-5 --augment")
