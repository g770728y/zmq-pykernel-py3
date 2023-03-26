# zmq-pykernel-py3
> https://github.com/fperez/zmq-pykernel
`zmq-pykernel`是一个ipython的client/server模型的原型程序, 使用python2\
为了研究如何在GUI程序中整合python命令行, 我将它升级到了python3

## 基本思路
- 程序分为client(frontend.py)和server(kernel.py)两大部分
- 在命令行中打开一个新的client，会在客户端与服务端同时建立一个session(Session.py)
- 在客户端输入时, 可以使用tab进行补全(completer)
- 在语句后输入;号, 可以延迟计算( 比如输入print(1); 不会回显, 再输入print(2)不带分号才会完成计算并回显)

## 主要技术
- zmq, ZeroMQ, 小有名气的MQ, 有多种语言实现, 支持分布式消息, 但消息不能持久化, 比较适用于当前场景
  在server维护两个socket: 
  - pub_socket用于发布命令结果(类型为zmq.PUB)
  - rep_socket用于接收命令(类型为zmq.ROUTER, 支持多路)

  同样, 在client端维护两个对应socket:
  - sub_socket用于订阅计算结果
  - res_socket用于发送客户输入的命令(类型为zmq.DEALEAR, 与ROUTER对应)

- 最核心的函数: python的exec方法
  exec有3个参数: source, globals, locals\
  最重要的是第3个参数locals, 相当于context\
  利用locals, 可以实现连续计算时中间值的维护

## 当前问题
- 由于使用了exec, 所以只有 print(1) 这样输出到stdout/stderr 里的值才会被返回客户端
- 有bug

