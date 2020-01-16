from mpdb import Mpdb


debugger = Mpdb()

# debugger.handle_user_command('Set breakpoints\n')
# debugger.set_break('main.py', 28, cond='some_value == 1')
debugger.set_trace()
# debugger.set_break('main.py', 36)


some_value = 0


def test():
    print('test1')


def test2():
    print('test2')


def more_test(arg1, arg2, arg3):
    print(arg1, arg2, arg3)
    return 50


def test_function():
    global some_value
    r = 0
    for i in range(3):
        print(some_value)
        some_value += 1
        r += i
    print("test_for_loop", r)

    # while loop
    r = 0
    i = 0
    test(), test2()
    more_test(1, '2', 3.1)
    while i < 3:
        r += i
        i += 1
    print("test_while_loop", i)


test_function()
debugger.set_quit()
