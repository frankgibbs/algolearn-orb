"""
Observer Design Pattern Concept
https://sbcode.net/python/observer/#observerobserver_conceptpy
"""
from abc import ABCMeta, abstractmethod
from src.core.constants import *
from ordered_set import OrderedSet
from threading import Lock
from queue import Queue

class IObservable(metaclass=ABCMeta):
    "The Subject Interface"    
    @staticmethod
    @abstractmethod
    def subscribe(observer):
        "The subscribe method"    @staticmethod
    @abstractmethod
    def unsubscribe(observer):
        "The unsubscribe method"    @staticmethod
    @abstractmethod
    def notify(observer):
        "The notify method"
    
class Subject(IObservable):
    
    "The Subject (Observable)"    
    def __init__(self):
        self._observers = OrderedSet()
        self.lock = Lock() 
        self.event_queue = Queue()

    def subscribe(self, observer):
       self._observers.add(observer)    
        
    def unsubscribe(self, observer):
        self._observers.remove(observer)    
    
    def notify(self, *args):
        for observer in self._observers:
            observer.notify(self, *args)

    def addToQueue(self, *args):
        self.lock.acquire()
        self.event_queue.put(args)  # Store the tuple as-is
        self.lock.release()

    def processQueue(self):
        self.lock.acquire()
        # Get all items from the queue and store them in a list
        items_to_process = []
        while not self.event_queue.empty():
            items_to_process.append(self.event_queue.get())
        self.lock.release()
        
        # Process all items
        for args in items_to_process:
            for observer in self._observers:
                observer.notify(self, *args)  # Unpack the tuple

   
class IObserver(metaclass=ABCMeta):
    "A method for the Observer to implement"    
    @staticmethod
    @abstractmethod
    def notify(observable, *args):
        "Receive notifications"
    